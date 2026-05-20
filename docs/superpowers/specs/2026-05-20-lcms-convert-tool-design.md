# LCMS 数据转化工具设计

## 背景

当前项目“工具服务”页签下尚未提供面向实验人员的 LCMS 数据转化能力。用户已有一套可工作的外部脚本，位于 `E:\LCMS\scripts\export_single_raw_apex_ms1.py`，能够将单个 Waters 数据目录转换为谱解可用的两列 MS 谱图数据。

本次需求目标不是简单调用外部脚本路径，而是将其核心方法整合进当前项目，在不依赖外部目录运行时导入的前提下，形成可在前端直接操作的正式工具页。

## 目标

- 在“工具服务”下新增 `LCMS 数据转化` 页签。
- 支持前端选择单个 Waters 数据目录，并由浏览器自动打包为 zip 上传。
- 后端解析上传目录，转换为谱解使用的两列 `csv` 格式 MS 谱图数据。
- 前端展示：
  - `retention time - intensity` 曲线
  - `m/z - intensity` 原始 MS 谱图
  - `m/z - intensity` 高峰视图
- 前端支持下载转换后的 `csv` 文件。
- 后端返回 `apex_rt`、`apex_tic` 等关键摘要信息，供前端展示和后续扩展使用。

## 非目标

- 不支持批量上传多个 Waters 数据目录。
- 不接入任务中心、异步任务流或历史记录。
- 不在本次实现中支持非 Waters 目录以外的复杂仪器格式适配。
- 不新增前端自动化测试或整套工具页测试体系。

## 用户流程

1. 用户进入“工具服务 / LCMS 数据转化”。
2. 用户选择本机单个 Waters 数据目录。
3. 前端读取目录内容并在浏览器端打包为 zip。
4. 用户点击“开始转换”。
5. 后端接收 zip、解压、识别目录、执行 `raw -> mzML -> TIC apex MS1` 提取。
6. 后端返回结果摘要、RT 曲线、MS 原始数据、MS 高峰视图数据、下载地址。
7. 前端展示图表，并允许下载 `csv`。

## 架构设计

### 前端

新增独立工具页：

- 路由：`/tools/lcms-convert`
- 视图：`frontend/src/views/ToolLcmsConvertView.vue`

页面由四个区域组成：

1. 目录上传区
2. 转换控制区
3. 结果摘要区
4. 图表展示区

前端目录上传采用浏览器目录选择能力读取目录，再使用已有依赖 `jszip` 自动打包，避免引入新的目录上传协议。

图表层分为两类：

- RT 曲线：复用现有 `SpectrumPreviewChart.vue`
- MS 峰图：新增 `MsStickSpectrumChart.vue`

### 后端

后端新增同步工具接口：

- `POST /tools/lcms-convert/run`
- `GET /tools/lcms-convert/download/{job_id}`

后端拆分三层：

1. 接口层：接收上传文件与返回统一响应
2. Schema 层：定义请求与响应模型
3. Service 层：完成解压、识别目录、调用 `msconvert`、解析 mzML、生成 CSV 与可视化数据

### 脚本整合原则

不直接依赖 `E:\LCMS\scripts\...` 外部路径运行，而是将以下核心方法迁移并工程化到项目内：

- `find_msconvert`
- `is_ascii_only`
- `build_safe_ascii_copy`
- `convert_raw_to_mzml`
- `extract_scan_time`
- `find_apex_spectrum`
- `save_csv`
- 峰标注选取逻辑

## 数据处理设计

### 输入目录

首版仅支持单个 Waters 数据目录。目录通常以 `.raw` 结尾，但不强依赖后缀；后端以目录结构识别为主，并兼容“设备导出目录不带 `.raw` 后缀”的情况。

### mzML 转换

后端使用 `msconvert.exe` 执行原始目录转换，查找顺序沿用现有脚本逻辑：

1. `PATH` 中查找
2. 常见安装路径查找
3. 指定基目录递归查找

若输入目录路径包含非 ASCII 字符，则在临时目录中复制一份 ASCII 别名目录后再执行转换，降低 `msconvert` 在中文路径下的兼容风险。

### Apex 谱图提取

处理逻辑沿用原脚本：

1. 遍历 mzML 中所有 `MS1` 扫描
2. 读取每个扫描的保留时间 `RT`
3. 对强度数组求和，得到当前扫描 `TIC`
4. 取 `TIC` 最大的扫描，记为 apex 扫描
5. 导出该扫描的 `m/z` 与 `Intensity` 为两列 `csv`

### RT 曲线

在遍历 `MS1` 扫描时，同时收集：

- `rt_x_values`
- `rt_y_values`

其中 `rt_y_values` 即每个扫描的 TIC，用于前端显示 `retention time - intensity` 曲线，并在 apex 位置高亮说明当前导出谱图来自峰顶扫描。

### MS 原始视图与高峰视图

原始脚本 `export_ms_spectra.py` 并未真正过滤谱图数据，而是：

- 保留全部峰绘图
- 只对满足条件的高峰做标注

本次在其基础上新增高峰视图，规则与原脚本口径保持一致：

- `ms_full_*`：保留全部 `m/z - intensity` 点
- `ms_filtered_*`：保留 `Intensity >= 最大峰强度 10%` 的点

### 峰标注逻辑

沿用 `export_ms_spectra.py` 的峰标注规则：

- 相对强度阈值：`10%`
- 峰间最小 `m/z` 间距：`8.0`
- 最多标注：`8` 个峰

后端返回 `label_peaks`，供前端高峰视图使用。

## 接口设计

### 运行接口

`POST /tools/lcms-convert/run`

请求：

- `file`: 浏览器端打包后的 zip 文件

响应数据包含：

- `job_id`
- `source_name`
- `apex_rt`
- `apex_tic`
- `rt_x_values`
- `rt_y_values`
- `ms_full_x_values`
- `ms_full_y_values`
- `ms_filtered_x_values`
- `ms_filtered_y_values`
- `label_peaks`
- `point_count_full`
- `point_count_filtered`
- `download_url`

### 下载接口

`GET /tools/lcms-convert/download/{job_id}`

返回转换生成的 `csv` 文件流，供前端直接下载。

## 前端交互设计

### 上传区

- 按钮文案：`选择 Waters 数据目录`
- 选中后展示：
  - 目录名
  - 文件数量
  - 总大小
- 说明：
  - 当前仅支持单个目录
  - 目录通常为 `.raw`
  - 上传前会自动打包为 zip

### 转换区

- 主按钮：`开始转换`
- 状态提示：
  - 正在打包目录
  - 正在上传
  - 正在解析 LCMS 数据
  - 正在生成谱图结果

### 结果摘要区

展示：

- 源目录名称
- Apex RT
- Apex TIC
- 原始点数
- 高峰点数
- `下载 CSV`

### 图表区

图表区拆分为两个卡片：

1. `RT-Intensity 曲线`
2. `MS 谱图`

其中 `MS 谱图` 提供两个视图切换：

- `原始谱图`
- `高峰视图`

原始谱图与高峰视图均采用 stick spectrum 风格，不使用连续折线来替代质谱峰图。

## 异常处理

首版覆盖以下必要异常：

- 未选择目录
- 目录读取或浏览器打包失败
- 上传文件为空或不是有效 zip
- 解压后未识别到有效 Waters 数据目录
- 未找到 `msconvert.exe`
- `mzML` 转换失败
- 未找到有效 `MS1`
- 输出 `csv` 失败

所有异常统一通过当前项目的 `ApiResponse` 错误语义返回，前端在工具页内展示明确错误提示。

## 验证策略

遵循项目当前约束，本次不默认扩大测试范围。

验证方式：

- 后端最小导入与接口连通验证
- 前端构建验证
- 工具页完整手工联调

若验证过程中需要临时脚本，仅作为临时文件使用，验证后删除，不残留无关文件。

## 文件影响范围

预计新增或修改以下文件：

- `backend/app/api/v1/endpoints/lcms_convert.py`
- `backend/app/api/v1/router.py`
- `backend/app/core/config.py`
- `backend/app/schemas/lcms_convert.py`
- `backend/app/services/lcms_convert_service.py`
- `backend/requirements.txt`
- `frontend/src/api/specAgentApi.js`
- `frontend/src/router/index.js`
- `frontend/src/App.vue`
- `frontend/src/components/MsStickSpectrumChart.vue`
- `frontend/src/views/ToolLcmsConvertView.vue`

## 成功标准

- 前端可选择单个 Waters 数据目录并成功打包上传。
- 后端可在项目内独立完成目录解压、转换与导出，不依赖外部脚本路径运行。
- 前端可以看到 RT 曲线、MS 原始谱图和高峰视图。
- 前端可以下载转换后的两列 `csv` 文件。
- 工具页整体风格与现有“工具服务”页签保持一致，但具备清晰、完整的单次处理体验。
