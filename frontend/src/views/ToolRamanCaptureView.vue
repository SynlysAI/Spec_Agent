<script setup>
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getApiErrorMessage, runRamanCapture } from '../api/specAgentApi'

const loading = ref(false)
const resultData = ref(null)

const form = reactive({
  instrument_ip: '10.26.15.56',
  callback_port: 9000,
  wavenumber_text: '800.0, 850.0, 900.0',
  power_text: '10.0, 50.0, 100.0',
})

const summary = computed(() => resultData.value?.summary || null)
const results = computed(() => resultData.value?.results || [])

/**
 * 将逗号分隔文本解析为数字列表。
 *
 * Args:
 *   text: 逗号分隔的数字文本。
 *
 * Returns:
 *   数字列表。
 */
function parseNumberList(text) {
  return String(text || '')
    .split(',')
    .map((item) => Number(item.trim()))
    .filter((value) => Number.isFinite(value))
}

/**
 * 格式化数字显示。
 *
 * Args:
 *   value: 原始数字。
 *   digits: 小数位数。
 *
 * Returns:
 *   格式化后的字符串。
 */
function formatNumber(value, digits = 3) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '-'
  }
  return Number(value).toFixed(digits)
}

/**
 * 提交拉曼批量采集请求。
 *
 * Returns:
 *   Promise<void>
 */
async function submitCapture() {
  const wavenumberList = parseNumberList(form.wavenumber_text)
  const powerList = parseNumberList(form.power_text)

  if (!form.instrument_ip.trim()) {
    ElMessage.warning('请输入仪器 IP')
    return
  }
  if (wavenumberList.length === 0) {
    ElMessage.warning('请输入至少一个中心波数')
    return
  }
  if (powerList.length === 0) {
    ElMessage.warning('请输入至少一个激光功率')
    return
  }

  loading.value = true
  resultData.value = null
  try {
    const data = await runRamanCapture(
      {
        instrument_ip: form.instrument_ip.trim(),
        callback_port: Number(form.callback_port),
        wavenumber_list: wavenumberList,
        power_list: powerList,
      },
      { timeout: 900000 },
    )
    resultData.value = data
    ElMessage.success(`采集完成：成功 ${data.summary?.success || 0} 个，失败 ${data.summary?.failed || 0} 个`)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <h3 class="panel-title">拉曼批量采集</h3>
    </div>
    <div class="panel-body">
      <el-row :gutter="16">
        <el-col :lg="10" :md="24">
          <el-card shadow="never" class="block-card">
            <template #header>
              <div class="card-header">采集参数</div>
            </template>
            <el-form label-position="top">
              <el-form-item label="仪器 IP">
                <el-input v-model="form.instrument_ip" placeholder="例如：10.26.15.56" />
              </el-form-item>
              <el-form-item label="回调端口">
                <el-input-number v-model="form.callback_port" :min="1" :max="65535" />
              </el-form-item>
              <el-form-item label="中心波数列表">
                <el-input
                  v-model="form.wavenumber_text"
                  type="textarea"
                  :rows="3"
                  placeholder="逗号分隔，例如：800.0, 850.0, 900.0"
                />
              </el-form-item>
              <el-form-item label="激光功率列表">
                <el-input
                  v-model="form.power_text"
                  type="textarea"
                  :rows="3"
                  placeholder="逗号分隔，例如：10.0, 50.0, 100.0"
                />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="loading" @click="submitCapture">开始批量采集</el-button>
              </el-form-item>
            </el-form>
            <el-alert
              type="info"
              :closable="false"
              show-icon
              title="说明"
              description="系统会按中心波数与激光功率组合顺序采集，完成后仅在页面展示报告，不保存到本地文件。"
            />
          </el-card>
        </el-col>

        <el-col :lg="14" :md="24">
          <el-card shadow="never" class="block-card result-card">
            <template #header>
              <div class="card-header">采集概览</div>
            </template>
            <el-empty v-if="!summary && !loading" description="暂无采集结果" />
            <el-skeleton v-else-if="loading" animated :rows="8" />
            <template v-else>
              <el-descriptions :column="2" border>
                <el-descriptions-item label="仪器地址">{{ resultData.instrument_ip }}</el-descriptions-item>
                <el-descriptions-item label="回调端口">{{ resultData.callback_port }}</el-descriptions-item>
                <el-descriptions-item label="回调地址">{{ resultData.callback_url }}</el-descriptions-item>
                <el-descriptions-item label="总耗时">{{ formatNumber(summary.duration_seconds) }} 秒</el-descriptions-item>
                <el-descriptions-item label="总任务">{{ summary.total }}</el-descriptions-item>
                <el-descriptions-item label="成功/失败">{{ summary.success }} / {{ summary.failed }}</el-descriptions-item>
              </el-descriptions>
            </template>
          </el-card>
        </el-col>
      </el-row>

      <el-card v-if="resultData" shadow="never" class="block-card">
        <template #header>
          <div class="card-header">采集明细</div>
        </template>
        <el-table :data="results" size="small" border max-height="420">
          <el-table-column prop="sequence" label="序号" width="80" />
          <el-table-column prop="wavenumber" label="中心波数" width="120" />
          <el-table-column prop="power" label="激光功率" width="120" />
          <el-table-column label="状态" width="100">
            <template #default="scope">
              <el-tag :type="scope.row.success ? 'success' : 'danger'" size="small">
                {{ scope.row.success ? '成功' : '失败' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="point_count" label="数据点" width="100" />
          <el-table-column label="强度范围" min-width="160">
            <template #default="scope">
              {{ formatNumber(scope.row.y_min) }} ~ {{ formatNumber(scope.row.y_max) }}
            </template>
          </el-table-column>
          <el-table-column label="耗时(s)" width="110">
            <template #default="scope">
              {{ formatNumber(scope.row.duration_seconds) }}
            </template>
          </el-table-column>
          <el-table-column prop="error_msg" label="错误信息" min-width="220" />
        </el-table>
      </el-card>

      <el-card v-if="resultData" shadow="never" class="block-card">
        <template #header>
          <div class="card-header">完成报告</div>
        </template>
        <pre class="report-preview">{{ resultData.report }}</pre>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.block-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  color: #2b3447;
}

.result-card {
  min-height: 360px;
}

.report-preview {
  max-height: 520px;
  overflow: auto;
  padding: 14px;
  margin: 0;
  background: #f7f9fc;
  border: 1px solid #d8e1ef;
  border-radius: 8px;
  color: #2b3447;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
