<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  createLabCollectRun,
  getApiErrorMessage,
  getLabCollectConfig,
  getLabCollectRun,
  getLabCollectRuns,
} from '../api/specAgentApi'

const loadingConfig = ref(false)
const loadingHistory = ref(false)
const creatingRun = ref(false)
const configData = ref(null)
const historyItems = ref([])
const activeRun = ref(null)
const pollingTimer = ref(null)

const selectedTypes = ref([])
const collectMode = ref('single')
const collectDate = ref('2026-04-17')
const dateRange = ref(['2026-04-17', '2026-04-17'])

const typeOptions = computed(() =>
  (configData.value?.items || []).map((item) => ({
    label: item.spectrum_type.toUpperCase(),
    value: item.spectrum_type,
    enabled: item.enabled,
    remoteRoot: item.remote_root,
    sampleMode: item.sample_mode,
  })),
)

const summaryCards = computed(() => {
  const summary = activeRun.value?.summary || {}
  return [
    { title: '候选样本', value: summary.total_candidates ?? 0 },
    { title: '新增导入', value: summary.imported ?? 0 },
    { title: '覆盖更新', value: summary.updated ?? 0 },
    { title: '失败数', value: summary.failed ?? 0 },
  ]
})

const activeProgress = computed(() => Number(activeRun.value?.summary?.progress || 0))
const activeTypeStats = computed(() => {
  const stats = activeRun.value?.summary?.type_stats || {}
  return Object.entries(stats).map(([type, value]) => ({
    type: String(type).toUpperCase(),
    candidates: Number(value?.candidates || 0),
    imported: Number(value?.imported || 0),
    updated: Number(value?.updated || 0),
    failed: Number(value?.failed || 0),
  }))
})

/**
 * 加载采集配置。
 *
 * Returns:
 *   Promise<void>
 */
async function loadConfig() {
  loadingConfig.value = true
  try {
    configData.value = await getLabCollectConfig()
    if (selectedTypes.value.length === 0) {
      selectedTypes.value = (configData.value?.items || [])
        .filter((item) => item.enabled)
        .map((item) => item.spectrum_type)
    }
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    loadingConfig.value = false
  }
}

/**
 * 加载采集历史。
 *
 * Returns:
 *   Promise<void>
 */
async function loadHistory() {
  loadingHistory.value = true
  try {
    const data = await getLabCollectRuns(20)
    historyItems.value = data?.items || []
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    loadingHistory.value = false
  }
}

/**
 * 构建采集请求参数。
 *
 * Returns:
 *   采集请求对象。
 */
function buildPayload() {
  if (collectMode.value === 'single') {
    return {
      collect_date: collectDate.value,
      spectrum_types: selectedTypes.value,
    }
  }
  return {
    date_from: dateRange.value?.[0],
    date_to: dateRange.value?.[1],
    spectrum_types: selectedTypes.value,
  }
}

/**
 * 启动采集。
 *
 * Returns:
 *   Promise<void>
 */
async function startCollect() {
  if (selectedTypes.value.length === 0) {
    ElMessage.warning('请至少选择一个实验类型')
    return
  }
  if (collectMode.value === 'single' && !collectDate.value) {
    ElMessage.warning('请选择采集日期')
    return
  }
  if (collectMode.value === 'range' && (!dateRange.value?.[0] || !dateRange.value?.[1])) {
    ElMessage.warning('请选择完整日期范围')
    return
  }
  creatingRun.value = true
  try {
    const created = await createLabCollectRun(buildPayload())
    ElMessage.success(`采集批次已创建：${created.run_id}`)
    await loadRun(created.run_id)
    await loadHistory()
    startPolling()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    creatingRun.value = false
  }
}

/**
 * 加载批次详情。
 *
 * Args:
 *   runId: 批次 ID。
 *
 * Returns:
 *   Promise<void>
 */
async function loadRun(runId) {
  if (!runId) {
    return
  }
  try {
    activeRun.value = await getLabCollectRun(runId)
    if (!['PENDING', 'QUEUED', 'RUNNING'].includes(String(activeRun.value?.status || ''))) {
      stopPolling()
    }
  } catch (error) {
    stopPolling()
    ElMessage.error(getApiErrorMessage(error))
  }
}

/**
 * 计算采集状态对应的标签类型。
 *
 * Args:
 *   status: 批次状态。
 *
 * Returns:
 *   Element Plus 标签类型。
 */
function getStatusTagType(status) {
  const normalized = String(status || '').toUpperCase()
  if (normalized === 'SUCCESS') {
    return 'success'
  }
  if (normalized === 'FAILED') {
    return 'danger'
  }
  if (normalized === 'PARTIAL_SUCCESS') {
    return 'warning'
  }
  if (['RUNNING', 'QUEUED', 'PENDING'].includes(normalized)) {
    return 'primary'
  }
  return 'info'
}

/**
 * 启动轮询。
 */
function startPolling() {
  stopPolling()
  pollingTimer.value = setInterval(() => {
    if (activeRun.value?.run_id) {
      loadRun(activeRun.value.run_id)
    }
  }, 2000)
}

/**
 * 停止轮询。
 */
function stopPolling() {
  if (!pollingTimer.value) {
    return
  }
  clearInterval(pollingTimer.value)
  pollingTimer.value = null
}

onMounted(async () => {
  await loadConfig()
  await loadHistory()
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<template>
  <div class="collect-page">
    <div class="collect-main-grid">
      <section class="panel collect-config-panel">
        <div class="panel-header">
          <h3 class="panel-title">采集参数</h3>
        </div>
        <div class="panel-body">
          <el-row :gutter="18">
            <el-col :span="9">
              <el-card shadow="never" class="inner-card">
                <template #header>
                  <div class="inner-card-title">配置摘要</div>
                </template>
                <el-skeleton :loading="loadingConfig" animated :rows="6">
                  <template #default>
                    <div class="config-line">配置文件：{{ configData?.config_path || '-' }}</div>
                    <div v-for="item in configData?.items || []" :key="item.spectrum_type" class="config-item">
                      <div class="config-item-title">
                        <span>{{ item.spectrum_type.toUpperCase() }}</span>
                        <el-tag size="small" :type="item.enabled ? 'success' : 'info'">
                          {{ item.enabled ? '已启用' : '未启用' }}
                        </el-tag>
                      </div>
                      <div class="config-path">{{ item.remote_root || '-' }}</div>
                    </div>
                  </template>
                </el-skeleton>
              </el-card>
            </el-col>

            <el-col :span="15">
              <el-form label-position="top">
                <el-form-item label="采集模式">
                  <el-radio-group v-model="collectMode">
                    <el-radio-button label="single">单日采集</el-radio-button>
                    <el-radio-button label="range">范围采集</el-radio-button>
                  </el-radio-group>
                </el-form-item>

                <el-form-item v-if="collectMode === 'single'" label="采集日期">
                  <el-date-picker
                    v-model="collectDate"
                    type="date"
                    value-format="YYYY-MM-DD"
                    format="YYYY-MM-DD"
                    placeholder="选择日期"
                    style="width: 100%"
                  />
                </el-form-item>

                <el-form-item v-else label="采集日期范围">
                  <el-date-picker
                    v-model="dateRange"
                    type="daterange"
                    value-format="YYYY-MM-DD"
                    format="YYYY-MM-DD"
                    range-separator="至"
                    start-placeholder="开始日期"
                    end-placeholder="结束日期"
                    style="width: 100%"
                  />
                </el-form-item>

                <el-form-item label="实验类型">
                  <el-select v-model="selectedTypes" multiple style="width: 100%">
                    <el-option
                      v-for="item in typeOptions"
                      :key="item.value"
                      :label="`${item.label} · ${item.sampleMode === 'directory' ? '目录样本' : '单文件样本'}`"
                      :value="item.value"
                      :disabled="!item.enabled"
                    />
                  </el-select>
                </el-form-item>

                <div class="form-actions">
                  <el-button type="primary" :loading="creatingRun" @click="startCollect">启动采集</el-button>
                  <el-button plain :loading="loadingHistory" @click="loadHistory">刷新历史</el-button>
                </div>
              </el-form>
            </el-col>
          </el-row>
        </div>
      </section>

      <section v-if="activeRun" class="panel collect-run-panel">
        <div class="panel-body">
          <el-card shadow="never" class="inner-card">
            <template #header>
              <div class="run-header">
                <div class="inner-card-title">当前批次（{{ activeRun.run_id }}）</div>
                <el-tag :type="getStatusTagType(activeRun.status)">{{ activeRun.status }}</el-tag>
              </div>
            </template>
            <div class="stat-grid collect-stat-grid">
              <div v-for="item in summaryCards" :key="item.title" class="stat-card">
                <div class="stat-title">{{ item.title }}</div>
                <div class="stat-value">{{ item.value }}</div>
              </div>
            </div>
            <el-descriptions :column="2" border class="run-desc">
              <el-descriptions-item label="触发模式">{{ activeRun.trigger_mode }}</el-descriptions-item>
              <el-descriptions-item label="日期范围">{{ activeRun.date_from }} ~ {{ activeRun.date_to }}</el-descriptions-item>
              <el-descriptions-item label="实验类型">{{ (activeRun.spectrum_types || []).join(', ') }}</el-descriptions-item>
              <el-descriptions-item label="失败数量">{{ activeRun.errors?.length || 0 }}</el-descriptions-item>
            </el-descriptions>
            <el-progress :percentage="activeProgress" :stroke-width="14" />
            <div v-if="activeTypeStats.length > 0" class="type-stat-section">
              <div class="type-stat-header">分类型采集统计</div>
              <div class="type-stat-grid">
                <div v-for="item in activeTypeStats" :key="item.type" class="type-stat-card">
                  <div class="type-stat-title">{{ item.type }}</div>
                  <div class="type-stat-line">候选 {{ item.candidates }}</div>
                  <div class="type-stat-line">新增 {{ item.imported }}</div>
                  <div class="type-stat-line">更新 {{ item.updated }}</div>
                  <div class="type-stat-line">失败 {{ item.failed }}</div>
                </div>
              </div>
            </div>
            <el-alert
              v-if="(activeRun.errors || []).length > 0"
              type="warning"
              :closable="false"
              show-icon
              :title="`存在 ${activeRun.errors.length} 条失败记录`"
              class="collect-alert"
            />
            <el-table v-if="(activeRun.errors || []).length > 0" :data="activeRun.errors" size="small" border max-height="220">
              <el-table-column prop="spectrum_type" label="类型" width="110" />
              <el-table-column prop="source_date" label="日期" width="120" />
              <el-table-column prop="sample_name" label="样本" min-width="180" />
              <el-table-column prop="error_message" label="错误信息" min-width="220" />
            </el-table>
          </el-card>
        </div>
      </section>

      <section class="panel collect-history-panel">
        <div class="panel-header">
          <h3 class="panel-title">采集历史</h3>
        </div>
        <div class="panel-body">
          <el-table :data="historyItems" size="small" border v-loading="loadingHistory" max-height="680">
            <el-table-column prop="run_id" label="批次ID" min-width="220" />
            <el-table-column prop="status" label="状态" min-width="110" />
            <el-table-column prop="date_from" label="起始日期" min-width="120" />
            <el-table-column prop="date_to" label="结束日期" min-width="120" />
            <el-table-column label="样本数" min-width="100">
              <template #default="scope">
                {{ scope.row.summary?.total_candidates ?? 0 }}
              </template>
            </el-table-column>
            <el-table-column label="导入/更新" min-width="120">
              <template #default="scope">
                {{ scope.row.summary?.imported ?? 0 }} / {{ scope.row.summary?.updated ?? 0 }}
              </template>
            </el-table-column>
            <el-table-column label="进度" min-width="100">
              <template #default="scope">
                {{ scope.row.summary?.progress ?? 0 }}%
              </template>
            </el-table-column>
            <el-table-column label="操作" min-width="100">
              <template #default="scope">
                <el-button link type="primary" @click="loadRun(scope.row.run_id)">查看</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.collect-page {
  display: grid;
  gap: 16px;
}

.form-actions {
  display: flex;
  gap: 10px;
  margin-top: 8px;
}

.form-actions .el-button {
  min-width: 136px;
  height: 42px;
  font-weight: 600;
}

.form-actions .el-button--primary {
  box-shadow: 0 10px 18px rgba(45, 112, 214, 0.22);
}

.collect-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
}

.inner-card {
  margin-bottom: 0;
  border-radius: 12px;
  border-color: #e1ebfa;
}

.inner-card-title {
  font-weight: 600;
  color: #2b3447;
}

.config-line {
  margin-bottom: 10px;
  color: #627089;
  font-size: 13px;
}

.config-item {
  padding: 10px 0;
  border-top: 1px solid #edf2fa;
}

.config-item:first-of-type {
  border-top: none;
  padding-top: 0;
}

.config-item-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  color: #2b3447;
}

.config-path {
  margin-top: 6px;
  color: #627089;
  font-size: 12px;
  word-break: break-all;
}

.collect-alert {
  margin-bottom: 16px;
}

.collect-stat-grid {
  margin-bottom: 14px;
}

.run-desc {
  margin-bottom: 14px;
}

.run-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.type-stat-section {
  margin: 16px 0;
}

.type-stat-header {
  margin-bottom: 10px;
  color: #314968;
  font-size: 13px;
  font-weight: 700;
}

.type-stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 10px;
}

.type-stat-card {
  padding: 12px;
  border: 1px solid #dbe7f7;
  border-radius: 12px;
  background: linear-gradient(180deg, #fbfdff 0%, #f3f7fd 100%);
}

.type-stat-title {
  margin-bottom: 8px;
  color: #1f3f71;
  font-size: 14px;
  font-weight: 700;
}

.type-stat-line {
  color: #5f7392;
  font-size: 12px;
  line-height: 1.8;
}

.collect-history-panel :deep(.el-table th.el-table__cell) {
  background: #f7faff;
}

@media (max-width: 1200px) {
  .collect-config-panel :deep(.el-col) {
    max-width: 100%;
    flex: 0 0 100%;
  }
}

@media (max-width: 1024px) {
  .form-actions .el-button {
    flex: 1;
  }
}

@media (max-width: 768px) {
  .form-actions {
    flex-direction: column;
  }
}
</style>
