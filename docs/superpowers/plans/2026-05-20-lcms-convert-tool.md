# LCMS 数据转化工具 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在工具服务中新增 LCMS 数据转化页，支持单个 Waters 数据目录上传、转换为两列 CSV、前端预览 RT 曲线与 MS 谱图，并支持下载结果。

**Architecture:** 前端新增 `LCMS 数据转化` 工具页，浏览器端读取单个目录并用 `jszip` 打包为 zip 上传。后端新增同步工具接口与独立转换服务，在项目内整合外部 LCMS 脚本核心逻辑，完成 zip 解压、目录识别、`msconvert` 转 mzML、提取 TIC apex MS1、生成 CSV 与预览数据。

**Tech Stack:** FastAPI、Pydantic、Vue 3、Element Plus、ECharts、JSZip、NumPy、Pandas、Pyteomics、ProteoWizard msconvert

---

### Task 1: 补充 LCMS 转换后端模型与服务骨架

**Files:**
- Create: `backend/app/schemas/lcms_convert.py`
- Create: `backend/app/services/lcms_convert_service.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: 定义 LCMS 转换响应模型**

```python
class LcmsConvertLabelPeak(BaseModel):
    mz: float = Field(description="峰位 m/z。")
    intensity: float = Field(description="峰强度。")


class LcmsConvertResultData(BaseModel):
    job_id: str = Field(description="本次转换任务 ID。")
    source_name: str = Field(description="源目录名称。")
    apex_rt: float = Field(description="TIC 顶点对应保留时间。")
    apex_tic: float = Field(description="TIC 顶点强度。")
    rt_x_values: list[float] = Field(default_factory=list, description="RT 横轴数据。")
    rt_y_values: list[float] = Field(default_factory=list, description="RT 纵轴数据。")
    ms_full_x_values: list[float] = Field(default_factory=list, description="原始 MS m/z。")
    ms_full_y_values: list[float] = Field(default_factory=list, description="原始 MS 强度。")
    ms_filtered_x_values: list[float] = Field(default_factory=list, description="高峰视图 m/z。")
    ms_filtered_y_values: list[float] = Field(default_factory=list, description="高峰视图强度。")
    label_peaks: list[LcmsConvertLabelPeak] = Field(default_factory=list, description="代表峰标注列表。")
    point_count_full: int = Field(default=0, description="原始谱点数。")
    point_count_filtered: int = Field(default=0, description="高峰视图点数。")
    download_url: str = Field(description="CSV 下载地址。")
```

- [ ] **Step 2: 在 requirements 中补充 pyteomics 依赖**

```text
pyteomics>=4.7.5
```

- [ ] **Step 3: 创建服务类骨架与常量**

```python
class LcmsConvertService:
    """LCMS 数据转化服务。"""

    MS_LABEL_MAX_COUNT = 8
    MS_LABEL_MIN_RELATIVE_INTENSITY = 0.10
    MS_LABEL_MIN_MZ_SPACING = 8.0
    FILTER_MIN_RELATIVE_INTENSITY = 0.10

    def run_from_zip(self, zip_bytes: bytes, upload_name: str) -> LcmsConvertResultData:
        """从上传 zip 执行 LCMS 转换。"""
```

- [ ] **Step 4: 运行最小导入验证**

Run: `conda run -n Spec_Agent python -c "from app.schemas.lcms_convert import LcmsConvertResultData; from app.services.lcms_convert_service import LcmsConvertService; print('ok')"`

Expected: 输出 `ok`，导入不报错。

### Task 2: 实现目录识别、mzML 转换与结果生成

**Files:**
- Modify: `backend/app/services/lcms_convert_service.py`

- [ ] **Step 1: 迁移 msconvert 查找与 ASCII 安全目录逻辑**

```python
@staticmethod
def find_msconvert() -> str:
    ...

@staticmethod
def is_ascii_only(path: Path) -> bool:
    ...

@staticmethod
def build_safe_ascii_copy(raw_dir: Path, temp_root: Path, alias: str) -> Path:
    ...
```

- [ ] **Step 2: 实现 zip 解压与目标目录识别**

```python
@staticmethod
def extract_zip_to_temp(zip_bytes: bytes, temp_root: Path) -> Path:
    ...

@staticmethod
def locate_waters_directory(extracted_root: Path) -> Path:
    ...
```

- [ ] **Step 3: 实现 mzML 转换与扫描遍历**

```python
@staticmethod
def convert_raw_to_mzml(raw_dir: Path, msconvert: str, temp_root: Path, alias: str) -> Path:
    ...

@staticmethod
def iter_ms1_trace_and_apex(mzml_path: Path) -> tuple[list[float], list[float], float, float, list[float], list[float]]:
    ...
```

- [ ] **Step 4: 实现高峰过滤与峰标注**

```python
@classmethod
def filter_ms_peaks(cls, mzs: list[float], intensities: list[float]) -> tuple[list[float], list[float]]:
    ...

@classmethod
def pick_label_peaks(cls, mzs: list[float], intensities: list[float]) -> list[LcmsConvertLabelPeak]:
    ...
```

- [ ] **Step 5: 实现 CSV 输出与最终响应拼装**

```python
def run_from_zip(self, zip_bytes: bytes, upload_name: str) -> LcmsConvertResultData:
    ...
```

- [ ] **Step 6: 运行最小服务验证**

Run: `conda run -n Spec_Agent python -c "from pathlib import Path; from app.services.lcms_convert_service import LcmsConvertService; print(LcmsConvertService.is_ascii_only(Path('E:/LCMS/data/RDa DATA')))"` 

Expected: 输出 `True` 或 `False`，服务方法可调用。

### Task 3: 暴露 LCMS 工具接口与下载接口

**Files:**
- Create: `backend/app/api/v1/endpoints/lcms_convert.py`
- Modify: `backend/app/api/v1/router.py`

- [ ] **Step 1: 创建运行接口**

```python
@router.post("/run", response_model=ApiResponse[LcmsConvertResultData])
def run_lcms_convert(file: UploadFile = File(...)) -> ApiResponse[LcmsConvertResultData]:
    ...
```

- [ ] **Step 2: 创建下载接口**

```python
@router.get("/download/{job_id}")
def download_lcms_convert_csv(job_id: str):
    ...
```

- [ ] **Step 3: 将路由挂载到 API 聚合模块**

```python
from app.api.v1.endpoints.lcms_convert import router as lcms_convert_router
...
api_router.include_router(lcms_convert_router, dependencies=[Depends(require_authenticated)])
```

- [ ] **Step 4: 运行接口导入验证**

Run: `conda run -n Spec_Agent python -c "from app.api.v1.endpoints.lcms_convert import run_lcms_convert; print(run_lcms_convert)"`

Expected: 输出函数对象，不报导入错误。

### Task 4: 补充前端 API 与图表组件

**Files:**
- Modify: `frontend/src/api/specAgentApi.js`
- Create: `frontend/src/components/MsStickSpectrumChart.vue`

- [ ] **Step 1: 新增 LCMS 转换 API 与下载 URL 构建函数**

```javascript
export async function runLcmsConvert(formData, options = {}) {
  const response = await apiClient.post('/tools/lcms-convert/run', formData, buildRequestConfig(options))
  return unwrapResponse(response)
}

export function buildLcmsConvertDownloadUrl(jobId) {
  return buildAbsoluteApiUrl(`/tools/lcms-convert/download/${encodeURIComponent(jobId)}`)
}
```

- [ ] **Step 2: 新增 MS stick 图组件**

```vue
<script setup>
const props = defineProps({
  xValues: { type: Array, default: () => [] },
  yValues: { type: Array, default: () => [] },
  title: { type: String, default: 'MS 谱图' },
  labelPeaks: { type: Array, default: () => [] },
})
</script>
```

- [ ] **Step 3: 运行前端引用检查**

Run: `rg -n "runLcmsConvert|buildLcmsConvertDownloadUrl|MsStickSpectrumChart" frontend/src -S`

Expected: 能看到新增 API 与组件定义。

### Task 5: 实现 LCMS 数据转化工具页并接入导航

**Files:**
- Create: `frontend/src/views/ToolLcmsConvertView.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: 新增路由与菜单项**

```javascript
import ToolLcmsConvertView from '../views/ToolLcmsConvertView.vue'
...
{ path: '/tools/lcms-convert', component: ToolLcmsConvertView },
```

```vue
<el-menu-item index="/tools/lcms-convert">LCMS 数据转化</el-menu-item>
```

- [ ] **Step 2: 实现目录选择、zip 打包与状态展示**

```javascript
async function handleDirectoryChange(event) {
  ...
}

async function buildZipFile() {
  ...
}
```

- [ ] **Step 3: 实现转换提交、结果展示与 CSV 下载**

```javascript
async function submitConvert() {
  ...
}

async function downloadCsv() {
  ...
}
```

- [ ] **Step 4: 完成 RT 曲线与 MS 视图切换布局**

```vue
<SpectrumPreviewChart ... />
<MsStickSpectrumChart v-if="activeMsView === 'full'" ... />
<MsStickSpectrumChart v-else ... />
```

- [ ] **Step 5: 运行前端构建验证**

Run: `npm run build`

Workdir: `E:\xx_project\Spec_Agent\frontend`

Expected: 构建成功，输出新的 `dist` 产物。

### Task 6: 进行后端导入验证与完整联调检查

**Files:**
- Modify: `backend/app/services/lcms_convert_service.py`
- Modify: `backend/app/api/v1/endpoints/lcms_convert.py`
- Modify: `frontend/src/views/ToolLcmsConvertView.vue`

- [ ] **Step 1: 运行后端导入与路由加载验证**

Run: `conda run -n Spec_Agent python -c "from app.main import app; print('routes', any('/tools/lcms-convert/run' in str(route.path) for route in app.routes))"`

Expected: 输出包含 `routes True`

- [ ] **Step 2: 运行前端生产构建验证**

Run: `npm run build`

Workdir: `E:\xx_project\Spec_Agent\frontend`

Expected: 构建成功，无语法错误。

- [ ] **Step 3: 手工联调说明**

Run: `conda run -n Spec_Agent python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`

Expected: 本地服务可启动，后续在浏览器访问工具页并手工验证目录选择、转换、图表展示与 CSV 下载。
