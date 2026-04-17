<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import SpectrumPreviewChart from '../components/SpectrumPreviewChart.vue'
import {
  getApiErrorMessage,
  getSpectrumSampleDetail,
  listSpectrumSamples,
  previewSpectrum,
} from '../api/specAgentApi'

const loading = ref(false)
const detailLoading = ref(false)
const previewLoading = ref(false)
const tableData = ref([])
const detailVisible = ref(false)
const activeDetail = ref(null)
const previewData = ref(null)

const query = ref({
  page: 1,
  page_size: 10,
  spectrum_type: '',
  source_date: '',
  sample_name: '',
})

const pagination = ref({
  total: 0,
  page: 1,
  page_size: 10,
})

const previewAxisConfig = computed(() => {
  const spectype = String(previewData.value?.spectype || '').toLowerCase()
  if (spectype === 'nmr') {
    return { xAxisName: '化学位移 (ppm)', yAxisName: '信号强度', inverseXAxis: true }
  }
  if (spectype === 'gpc') {
    return { xAxisName: '时间 (min)', yAxisName: '信号强度 (μRIU)', inverseXAxis: false }
  }
  if (spectype === 'lcms') {
    return { xAxisName: 'm/z', yAxisName: '信号强度', inverseXAxis: false }
  }
  return { xAxisName: '波数 (cm⁻¹)', yAxisName: '强度', inverseXAxis: false }
})

const sampleMetaRows = computed(() => toRows(activeDetail.value?.sample?.sample_meta || {}))
const sourceRows = computed(() => toRows(activeDetail.value?.sample?.source || {}))
const storageRows = computed(() => toRows(activeDetail.value?.sample?.storage || {}))

/**
 * 对象转可展示键值数组。
 *
 * Args:
 *   source: 原始对象。
 *
 * Returns:
 *   键值数组。
 */
function toRows(source) {
  return Object.entries(source || {}).map(([key, value]) => ({
    key,
    value: typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value),
  }))
}

/**
 * 查询样本列表。
 *
 * Returns:
 *   Promise<void>
 */
async function fetchSamples() {
  loading.value = true
  try {
    const data = await listSpectrumSamples({
      page: query.value.page,
      page_size: query.value.page_size,
      spectrum_type: query.value.spectrum_type || undefined,
      source_date: query.value.source_date || undefined,
      sample_name: query.value.sample_name || undefined,
    })
    tableData.value = data.items || []
    pagination.value = {
      total: data.total || 0,
      page: data.page || query.value.page,
      page_size: data.page_size || query.value.page_size,
    }
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

/**
 * 重置筛选条件。
 */
function resetFilters() {
  query.value = {
    page: 1,
    page_size: 10,
    spectrum_type: '',
    source_date: '',
    sample_name: '',
  }
  fetchSamples()
}

/**
 * 打开样本详情。
 *
 * Args:
 *   sampleId: 样本 ID。
 *
 * Returns:
 *   Promise<void>
 */
async function openDetail(sampleId) {
  if (!sampleId) {
    return
  }
  detailVisible.value = true
  detailLoading.value = true
  previewData.value = null
  try {
    activeDetail.value = await getSpectrumSampleDetail(sampleId)
    await loadPreview()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    detailLoading.value = false
  }
}

/**
 * 加载样本谱图预览。
 *
 * Returns:
 *   Promise<void>
 */
async function loadPreview() {
  const analysisInput = activeDetail.value?.sample?.analysis_input || {}
  const spectrumType = activeDetail.value?.sample?.spectrum_type
  if (!analysisInput?.input_path || !spectrumType) {
    previewData.value = null
    return
  }
  const formData = new FormData()
  formData.append('spectype', spectrumType)
  formData.append('input_path', analysisInput.input_path)
  formData.append('max_points', '4096')
  previewLoading.value = true
  try {
    previewData.value = await previewSpectrum(formData)
  } catch (error) {
    previewData.value = null
    ElMessage.warning(`预览加载失败：${getApiErrorMessage(error)}`)
  } finally {
    previewLoading.value = false
  }
}

onMounted(fetchSamples)
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <h3 class="panel-title">样本管理</h3>
      <div>
        <el-button @click="resetFilters">重置</el-button>
        <el-button type="primary" plain @click="fetchSamples">刷新</el-button>
      </div>
    </div>
    <div class="panel-body">
      <el-form :inline="true">
        <el-form-item label="实验类型">
          <el-select v-model="query.spectrum_type" style="width: 140px" @change="query.page = 1; fetchSamples()">
            <el-option label="全部" value="" />
            <el-option label="NMR" value="nmr" />
            <el-option label="GPC" value="gpc" />
            <el-option label="IR" value="ir" />
            <el-option label="Raman" value="raman" />
            <el-option label="LCMS" value="lcms" />
          </el-select>
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker
            v-model="query.source_date"
            type="date"
            value-format="YYYY-MM-DD"
            format="YYYY-MM-DD"
            placeholder="全部"
            style="width: 160px"
            @change="query.page = 1; fetchSamples()"
          />
        </el-form-item>
        <el-form-item label="样品名">
          <el-input
            v-model="query.sample_name"
            placeholder="支持模糊搜索"
            style="width: 220px"
            clearable
            @keyup.enter="query.page = 1; fetchSamples()"
            @clear="query.page = 1; fetchSamples()"
          />
        </el-form-item>
      </el-form>

      <el-table :data="tableData" v-loading="loading" stripe>
        <el-table-column prop="sample_name" label="样品名" min-width="220" />
        <el-table-column prop="spectrum_type" label="类型" width="100" />
        <el-table-column prop="source_date" label="日期" width="120" />
        <el-table-column prop="collect_status" label="状态" width="120" />
        <el-table-column prop="latest_run_id" label="最近批次" min-width="180" />
        <el-table-column label="分析入口" min-width="260">
          <template #default="scope">
            {{ scope.row.analysis_input?.input_path || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="scope">
            <el-button type="primary" link @click="openDetail(scope.row.sample_id)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top: 14px; display: flex; justify-content: flex-end">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          background
          layout="total, sizes, prev, pager, next"
          :total="pagination.total"
          :page-sizes="[10, 20, 50]"
          @current-change="fetchSamples"
          @size-change="query.page = 1; fetchSamples()"
        />
      </div>
    </div>
  </div>

  <el-drawer v-model="detailVisible" title="样本详情与预览" size="55%" destroy-on-close>
    <div v-loading="detailLoading">
      <template v-if="activeDetail?.sample">
        <el-descriptions :column="2" border class="detail-block">
          <el-descriptions-item label="样本名">{{ activeDetail.sample.sample_name }}</el-descriptions-item>
          <el-descriptions-item label="实验类型">{{ activeDetail.sample.spectrum_type }}</el-descriptions-item>
          <el-descriptions-item label="日期">{{ activeDetail.sample.source_date }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ activeDetail.sample.collect_status }}</el-descriptions-item>
          <el-descriptions-item label="分析输入类型">{{ activeDetail.sample.analysis_input?.input_type || '-' }}</el-descriptions-item>
          <el-descriptions-item label="分析输入路径">{{ activeDetail.sample.analysis_input?.input_path || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="detail-block">
          <div class="detail-title">谱图预览</div>
          <div v-loading="previewLoading">
            <SpectrumPreviewChart
              v-if="previewData?.x_values?.length"
              :x-values="previewData.x_values"
              :y-values="previewData.y_values"
              :x-axis-name="previewAxisConfig.xAxisName"
              :y-axis-name="previewAxisConfig.yAxisName"
              :inverse-x-axis="previewAxisConfig.inverseXAxis"
              :title="`${activeDetail.sample.sample_name} 谱图预览`"
            />
            <el-empty v-else description="暂无可预览谱图" />
          </div>
        </div>

        <div class="detail-block detail-grid">
          <el-card shadow="never">
            <template #header><span>来源信息</span></template>
            <el-table :data="sourceRows" size="small" border>
              <el-table-column prop="key" label="字段" width="160" />
              <el-table-column prop="value" label="取值" />
            </el-table>
          </el-card>
          <el-card shadow="never">
            <template #header><span>存储信息</span></template>
            <el-table :data="storageRows" size="small" border>
              <el-table-column prop="key" label="字段" width="160" />
              <el-table-column prop="value" label="取值" />
            </el-table>
          </el-card>
        </div>

        <div class="detail-block">
          <div class="detail-title">样本元数据</div>
          <el-table :data="sampleMetaRows" size="small" border>
            <el-table-column prop="key" label="字段" width="200" />
            <el-table-column prop="value" label="取值" />
          </el-table>
        </div>

        <div class="detail-block">
          <div class="detail-title">文件清单</div>
          <el-table :data="activeDetail.files || []" size="small" border max-height="260">
            <el-table-column prop="file_name" label="文件名" min-width="220" />
            <el-table-column prop="role" label="角色" width="150" />
            <el-table-column prop="file_ext" label="后缀" width="80" />
            <el-table-column prop="relative_path" label="相对路径" min-width="220" />
            <el-table-column prop="is_primary_input" label="主输入" width="90">
              <template #default="scope">
                {{ scope.row.is_primary_input ? '是' : '否' }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </div>
  </el-drawer>
</template>

<style scoped>
.detail-block {
  margin-bottom: 18px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.detail-title {
  margin-bottom: 10px;
  font-weight: 600;
  color: #2b3447;
}

@media (max-width: 1200px) {
  .detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>

