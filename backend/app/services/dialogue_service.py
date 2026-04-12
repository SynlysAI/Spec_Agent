"""问答对话服务。"""

from __future__ import annotations

import importlib
from datetime import datetime
from typing import Any

from app.infra.mongo import get_results_collection, get_tasks_collection
from app.models.dialogue import DialogueReportItem

ANALYSIS_TYPE_LABELS = {
    "none": "无",
    "gpc": "GPC 凝胶色谱",
    "nmr": "NMR 核磁",
    "ir": "IR 红外",
    "raman": "Raman 拉曼",
}

ANALYSIS_TYPE_TO_TASK_KIND = {
    "gpc": "gpc_analysis",
    "nmr": "nmr_analysis",
    "ir": "ir_analysis",
    "raman": "raman_analysis",
}


class DialogueService:
    """提供问答页面所需的数据检索与规则回答能力。"""

    @staticmethod
    def list_analysis_types() -> list[dict[str, Any]]:
        """列出分析类型及其报告数量。

        Returns:
            分析类型列表，每项包含编码、中文名称和报告数量。
        """
        task_collection = get_tasks_collection()
        items: list[dict[str, Any]] = []
        for analysis_type, label in ANALYSIS_TYPE_LABELS.items():
            if analysis_type == "none":
                items.append({"analysis_type": analysis_type, "label": label, "report_count": 0})
                continue
            task_type = ANALYSIS_TYPE_TO_TASK_KIND[analysis_type]
            report_count = task_collection.count_documents(
                {"task_type": task_type, "status": "SUCCESS", "result_ref": {"$ne": None}}
            )
            items.append({"analysis_type": analysis_type, "label": label, "report_count": int(report_count)})
        return items

    @staticmethod
    def list_reports(analysis_type: str, limit: int = 20) -> list[DialogueReportItem]:
        """查询指定分析类型的历史报告。

        Args:
            analysis_type: 分析类型。
            limit: 返回数量上限。

        Returns:
            报告列表。
        """
        if analysis_type not in ANALYSIS_TYPE_TO_TASK_KIND:
            return []
        task_type = ANALYSIS_TYPE_TO_TASK_KIND[analysis_type]
        tasks_cursor = (
            get_tasks_collection()
            .find(
                {"task_type": task_type, "status": "SUCCESS", "result_ref": {"$ne": None}},
                {"_id": 0, "task_id": 1, "result_ref": 1, "created_at": 1},
            )
            .sort([("created_at", -1)])
            .limit(max(limit, 1))
        )

        result_collection = get_results_collection()
        items: list[DialogueReportItem] = []
        for task_doc in tasks_cursor:
            result_ref = task_doc.get("result_ref")
            if not result_ref:
                continue
            result_doc = result_collection.find_one({"result_id": result_ref}, {"_id": 0, "text_report": 1})
            text_report = str((result_doc or {}).get("text_report", "")).strip()
            snippet = text_report.replace("\n", " ")[:160]
            created_at = task_doc.get("created_at")
            created_text = (
                created_at.strftime("%Y-%m-%d %H:%M:%S")
                if isinstance(created_at, datetime)
                else str(created_at or "")
            )
            task_id = str(task_doc.get("task_id", ""))
            items.append(
                DialogueReportItem(
                    report_id=str(result_ref),
                    task_id=task_id,
                    title=f"{ANALYSIS_TYPE_LABELS.get(analysis_type, analysis_type)} 报告 - {task_id}",
                    created_at=created_text,
                    snippet=snippet,
                )
            )
        return items

    @staticmethod
    def generate_answer(
        question: str,
        analysis_type: str,
        report_id: str | None = None,
        history: list[dict[str, str]] | None = None,
        system_prompt: str | None = None,
    ) -> tuple[str, str]:
        """按规则生成问答回复。

        Args:
            question: 用户问题。
            analysis_type: 分析类型。
            report_id: 报告 ID。
            history: 最近历史消息。

        Returns:
            (回答内容, 使用片段) 二元组。
        """
        report_text = ""
        if report_id:
            doc = get_results_collection().find_one({"result_id": report_id}, {"_id": 0, "text_report": 1})
            report_text = str((doc or {}).get("text_report", "")).strip()

        used_excerpt = DialogueService._extract_relevant_excerpt(report_text=report_text, question=question)
        llm_answer = DialogueService._generate_answer_with_llm(
            question=question,
            analysis_type=analysis_type,
            report_text=report_text,
            history=history or [],
            system_prompt=system_prompt,
        )
        if llm_answer:
            return llm_answer, used_excerpt

        context_line = f"分析类型：{ANALYSIS_TYPE_LABELS.get(analysis_type, analysis_type)}"
        history_line = ""
        if history:
            history_line = f"，已参考最近 {min(len(history), 6)} 条会话上下文"

        if used_excerpt:
            answer = (
                f"基于已选报告的检索结果，先给你结论：\n\n"
                f"{used_excerpt}\n\n"
                f"如需我继续，可按你关心的方向追问（例如峰位、峰面积、模型参数或误差项）。\n"
                f"（{context_line}{history_line}）"
            )
        else:
            answer = (
                "当前未检索到可直接引用的报告片段。"
                "你可以先在右侧选择一份历史报告，再提问具体问题（例如“总结结论”“异常点在哪里”“参数是否合理”）。\n"
                f"（{context_line}{history_line}）"
            )
        return answer, used_excerpt

    @staticmethod
    def _extract_relevant_excerpt(report_text: str, question: str) -> str:
        """从报告中提取与问题相关的片段。

        Args:
            report_text: 报告全文。
            question: 用户问题。

        Returns:
            规则匹配到的文本片段。
        """
        if not report_text:
            return ""
        normalized_question = question.strip().lower()
        lines = [line.strip() for line in report_text.splitlines() if line.strip()]
        if not lines:
            return ""

        keywords = [token for token in normalized_question.replace("，", " ").replace(",", " ").split(" ") if token]
        matched: list[str] = []
        if keywords:
            for line in lines:
                line_lower = line.lower()
                if any(keyword in line_lower for keyword in keywords):
                    matched.append(line)
                if len(matched) >= 6:
                    break

        if not matched:
            matched = lines[:6]
        excerpt = "\n".join([f"- {item}" for item in matched[:6]])
        return excerpt[:1200]

    @staticmethod
    def _generate_answer_with_llm(
        question: str,
        analysis_type: str,
        report_text: str,
        history: list[dict[str, str]],
        system_prompt: str | None,
    ) -> str:
        """使用 LLM 生成问答结果，失败时返回空字符串。

        Args:
            question: 用户问题。
            analysis_type: 分析类型编码。
            report_text: 报告全文。
            history: 历史消息列表。
            system_prompt: 用户自定义提示词。

        Returns:
            LLM 回答文本，失败时返回空字符串。
        """
        try:
            model_module = importlib.import_module("llm_server.model")
            create_llm_client = getattr(model_module, "create_llm_client")
            llm_client = create_llm_client()

            langchain_messages = importlib.import_module("langchain_core.messages")
            SystemMessage = getattr(langchain_messages, "SystemMessage")
            HumanMessage = getattr(langchain_messages, "HumanMessage")
            AIMessage = getattr(langchain_messages, "AIMessage")

            merged_system_prompt = DialogueService._build_llm_system_prompt(
                analysis_type=analysis_type,
                report_text=report_text,
                user_prompt=system_prompt,
            )
            messages: list = [SystemMessage(content=merged_system_prompt)]

            for item in history[-8:]:
                role = str(item.get("role", "")).lower()
                content = str(item.get("content", "")).strip()
                if not content:
                    continue
                if role == "assistant":
                    messages.append(AIMessage(content=content))
                else:
                    messages.append(HumanMessage(content=content))
            messages.append(HumanMessage(content=question))

            response = llm_client.invoke(messages)
            content = getattr(response, "content", "")
            if isinstance(content, list):
                text_parts: list[str] = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(str(block.get("text", "")))
                    else:
                        text_parts.append(str(block))
                return "\n".join([item for item in text_parts if item]).strip()
            return str(content).strip()
        except Exception:
            return ""

    @staticmethod
    def _build_llm_system_prompt(analysis_type: str, report_text: str, user_prompt: str | None) -> str:
        """构建 LLM 系统提示词。

        Args:
            analysis_type: 分析类型。
            report_text: 报告文本。
            user_prompt: 用户输入的基础提示词。

        Returns:
            组合后的提示词。
        """
        base_prompt = (
            user_prompt.strip()
            if user_prompt and user_prompt.strip()
            else "你是一个专业的谱图分析助手，请基于报告内容回答用户问题，先给结论，再给依据。"
        )
        label = ANALYSIS_TYPE_LABELS.get(analysis_type, analysis_type)
        if report_text:
            return (
                f"{base_prompt}\n\n"
                f"当前分析类型：{label}\n"
                "以下是可参考的分析报告内容，请优先依据报告回答：\n"
                f"{report_text[:12000]}"
            )
        return f"{base_prompt}\n\n当前分析类型：{label}\n当前没有选中报告，请引导用户先选择报告后再进行细节问答。"


dialogue_service = DialogueService()
