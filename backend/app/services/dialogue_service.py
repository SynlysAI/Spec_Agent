"""问答对话服务。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.infra.repositories import ResultRepository, TaskRepository
from app.schemas.task_runtime import ResultRecord
from app.schemas.dialogue import DialogueReportItem
from app.services.dialogue_model_service import dialogue_model_service

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
    def list_models() -> list[dict[str, str]]:
        """列出问答模型选项。

        Returns:
            问答模型列表。
        """
        return dialogue_model_service.list_models()

    @staticmethod
    def get_default_model_key() -> str:
        """获取默认问答模型键。

        Returns:
            默认模型键。
        """
        return dialogue_model_service.get_default_model_key()

    @staticmethod
    def list_analysis_types(current_user: dict[str, str] | None = None) -> list[dict[str, Any]]:
        """列出分析类型及其报告数量。

        Args:
            current_user: 当前登录用户上下文。

        Returns:
            分析类型列表，每项包含编码、中文名称和报告数量。
        """
        items: list[dict[str, Any]] = []
        for analysis_type, label in ANALYSIS_TYPE_LABELS.items():
            if analysis_type == "none":
                items.append({"analysis_type": analysis_type, "label": label, "report_count": 0})
                continue
            task_type = ANALYSIS_TYPE_TO_TASK_KIND[analysis_type]
            report_count = TaskRepository.count(
                DialogueService._build_report_task_query(
                    task_type=task_type,
                    current_user=current_user,
                )
            )
            items.append({"analysis_type": analysis_type, "label": label, "report_count": int(report_count)})
        return items

    @staticmethod
    def list_reports(
        analysis_type: str,
        limit: int = 20,
        current_user: dict[str, str] | None = None,
    ) -> list[DialogueReportItem]:
        """查询指定分析类型的历史报告。

        Args:
            analysis_type: 分析类型。
            limit: 返回数量上限。
            current_user: 当前登录用户上下文。

        Returns:
            报告列表。
        """
        if analysis_type not in ANALYSIS_TYPE_TO_TASK_KIND:
            return []
        task_type = ANALYSIS_TYPE_TO_TASK_KIND[analysis_type]
        tasks_cursor = TaskRepository.find_many(
            query=DialogueService._build_report_task_query(
                task_type=task_type,
                current_user=current_user,
            ),
            projection={"_id": 0, "task_id": 1, "result_ref": 1, "created_at": 1},
            limit=max(limit, 1),
        )

        items: list[DialogueReportItem] = []
        for task_doc in tasks_cursor:
            result_ref = task_doc.get("result_ref")
            if not result_ref:
                continue
            result_doc = ResultRepository.find_raw(str(result_ref), {"_id": 0, "text_report": 1})
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
        model_key: str,
        question: str,
        analysis_type: str,
        report_id: str | None = None,
        history: list[dict[str, str]] | None = None,
        system_prompt: str | None = None,
        current_user: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        """按规则生成问答回复。

        Args:
            model_key: 问答模型键。
            question: 用户问题。
            analysis_type: 分析类型。
            report_id: 报告 ID。
            history: 最近历史消息。
            system_prompt: 用户自定义系统提示词。
            current_user: 当前登录用户上下文。

        Returns:
            (回答内容, 使用片段) 二元组。
        """
        report_text = ""
        if report_id:
            report_record = DialogueService._get_accessible_report(
                report_id=report_id,
                analysis_type=analysis_type,
                current_user=current_user,
            )
            if not report_record:
                raise ValueError("所选报告不存在或无权访问")
            report_text = str(report_record.text_report or "").strip()

        used_excerpt = DialogueService._extract_relevant_excerpt(report_text=report_text, question=question)
        llm_answer = DialogueService._generate_answer_with_llm(
            model_key=model_key,
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
    def _build_report_task_query(task_type: str, current_user: dict[str, str] | None) -> dict[str, Any]:
        """构建问答报告查询条件。

        Args:
            task_type: 任务类型。
            current_user: 当前登录用户上下文。

        Returns:
            问答报告对应的任务查询条件。
        """
        query: dict[str, Any] = {
            "task_type": task_type,
            "status": "SUCCESS",
            "result_ref": {"$ne": None},
        }
        if current_user and current_user.get("role") != "admin":
            query["created_by"] = current_user["user_id"]
        return query

    @staticmethod
    def _get_accessible_report(
        report_id: str,
        analysis_type: str,
        current_user: dict[str, str] | None,
    ) -> ResultRecord | None:
        """解析当前用户可访问的报告记录。

        Args:
            report_id: 报告 ID。
            analysis_type: 当前分析类型。
            current_user: 当前登录用户上下文。

        Returns:
            可访问的报告记录；不存在或无权限时返回 `None`。
        """
        expected_task_type = ANALYSIS_TYPE_TO_TASK_KIND.get(analysis_type)
        if not expected_task_type:
            return None

        result_record = ResultRepository.find_by_result_id(report_id)
        if not result_record:
            return None
        if result_record.task_type != expected_task_type:
            return None
        if DialogueService._can_access_report(result_record=result_record, current_user=current_user):
            return result_record
        return None

    @staticmethod
    def _can_access_report(result_record: ResultRecord, current_user: dict[str, str] | None) -> bool:
        """判断当前用户是否可访问报告记录。

        Args:
            result_record: 任务结果记录。
            current_user: 当前登录用户上下文。

        Returns:
            是否有权限访问该报告。
        """
        if not current_user:
            return True
        if current_user.get("role") == "admin":
            return True
        if result_record.created_by == current_user.get("user_id"):
            return True

        task_record = TaskRepository.find_by_task_id(result_record.task_id)
        if not task_record:
            return False
        return task_record.created_by == current_user.get("user_id")

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
        model_key: str,
        question: str,
        analysis_type: str,
        report_text: str,
        history: list[dict[str, str]],
        system_prompt: str | None,
    ) -> str:
        """使用指定问答模型生成回复。

        Args:
            model_key: 问答模型键。
            question: 用户问题。
            analysis_type: 分析类型编码。
            report_text: 报告全文。
            history: 历史消息列表。
            system_prompt: 用户自定义提示词。

        Returns:
            LLM 回答文本。
        """
        merged_system_prompt = DialogueService._build_llm_system_prompt(
            analysis_type=analysis_type,
            report_text=report_text,
            user_prompt=system_prompt,
        )
        messages: list[dict[str, str]] = [
            {"role": "system", "content": merged_system_prompt}
        ]

        for item in history[-8:]:
            role = str(item.get("role", "")).lower()
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            normalized_role = "assistant" if role == "assistant" else "user"
            messages.append({"role": normalized_role, "content": content})
        messages.append({"role": "user", "content": question})
        return dialogue_model_service.chat(model_key=model_key, messages=messages)

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
