# 谱图解析 CLI 用法（GPC / NMR / IR / Raman）

本文档汇总 `agents/` 目录下用于“从谱图文件解析结果”的脚本参数与命令行示例。四类谱图对应的脚本如下：

- GPC：`agents/langraph_gpc_agent.py`
- NMR：`agents/langraph_nmr_agent.py`
- IR/Raman：`agents/ir_raman_agent.py`（同一脚本，需用 `--spectype` 区分）

---

## 通用输出说明

1. 默认会把分析报告（Markdown 文本）打印到标准输出（stdout）。
2. 通过 `--report-path` 可以把报告写到指定 `.md` 文件。

---

## 1. NMR（Bruker 样品目录）

输入：一个 **Bruker 样品数据目录**（通常是包含处理/参数子目录的文件夹）。

脚本：

```bash
python agents/langraph_nmr_agent.py <input_path> --internal-standard-idx 0 --report-path outputs/nmr_report.md
```

常用参数：

- `<input_path>`：Bruker 样品目录路径
- `--internal-standard-idx`：内标峰索引（默认 `0`）
- `--output-dir`：结果输出根目录（默认使用配置里的默认目录）
- `--threshold`（默认 `0.01`）
- `--min-distance`（默认 `0.3`）
- `--min-prominence`（默认 `0.01`）
- `--width-multiplier`（默认 `1.0`）
- `--baseline-degree`（默认 `3`）
- `--smooth-window`（默认 `5`）
- `--detection-range-mode`（默认 `全谱`）
- `--detection-range-min` / `--detection-range-max`
- `--ppm-offset`（默认 `0.0`）

写入报告：

- `--report-path <path.md>`

---

## 2. GPC（.arw 文件 / 目录递归）

输入：

- 单个 `.arw` 文件，或
- 包含 `.arw` 的目录（会递归查找 `.arw`）。

脚本：

```bash
python agents/langraph_gpc_agent.py <input_path> --detect-mode auto --report-path outputs/gpc_report.md
```

常用参数：

- `<input_path>`：输入 `.arw` 文件或目录路径
- `--detect-mode`：峰检测模式（`auto` 默认；`manual` 需额外提供 `--manual-interval`）
- `--manual-interval`：手动时间区间，格式为 `start,end`（例如 `7.2,8.9`）
- 三色显式覆盖（可选）：
- `--green-arw <path>`
- `--red-arw <path>`
- `--white-arw <path>`
- 校准文件（可选）：
- `--calibration-file <path>`（`.json` 或 `.pdf`）
- 对比用 PDF（可选）：
- `--comparison-pdf <path>`
- LLM 解读（可选）：
- `--enable-llm`
- 写入报告：
- `--report-path <path.md>`

---

## 3. IR（红外光谱）

输入文件格式（脚本会解析为两列数值 `x, y`）：

- `txt` / `csv` 均可
- 文件每行应至少包含两列可解析为浮点数的数据；逗号会被当作分隔符处理
- `x` 是波数（cm-1）或类似坐标；`y` 是强度值（单位视你的数据而定）

脚本：

```bash
python agents/ir_raman_agent.py <spectrum_file> --spectype ir --mode greedy_decode --x0 400 --x1 4000 --report-path outputs/ir_report.md
```

常用参数：

- `<spectrum_file>`：谱图文件路径（`txt/csv`）
- `--spectype`：`ir`（默认）或 `raman`
- `--mode`（预测模式）：`greedy_decode`（默认）/ `beam_search` / `retrieval` / `function_groups`
- `--k`：`beam_search` / `retrieval` 候选数（默认 `3`）
- `--x0` / `--x1`：分析范围（默认 `400` 到 `4000`）
- `--transmittance`：仅 IR 有效；透射谱转为吸光度
- `--device`：`cpu` / `cuda`（默认不指定，代码会自动选择环境可用的设备）
- `--report-path <path.md>`

---

## 4. Raman（拉曼光谱）

与 IR 完全相同的输入格式与参数，只需要把 `--spectype` 改为 `raman`：

```bash
python agents/ir_raman_agent.py <spectrum_file> --spectype raman --mode beam_search --k 5 --x0 400 --x1 4000 --report-path outputs/raman_report.md
```
