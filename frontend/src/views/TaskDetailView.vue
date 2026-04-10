<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getTaskArtifacts, getTaskResult, getTaskStatus } from '../api/specAgentApi'

const route = useRoute()
const taskId = computed(() => route.params.taskId)

const loading = ref(false)
const statusData = ref(null)
const resultData = ref(null)
const artifactItems = ref([])

const structuredData = computed(() => resultData.value?.result?.structured_data || {})
const isNmrTask = computed(() => statusData.value?.task_type === 'nmr_analysis')
const isGpcTask = computed(() => statusData.value?.task_type === 'gpc_analysis')
const imageArtifacts = computed(() => artifactItems.value.filter((item) => item.file_type === 'image'))
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1'
const backendOrigin = new URL(apiBaseUrl).origin

/**
 * 构建可访问的图片 URL。
 *
 * Args:
 *   relativeUrl: 后端返回的静态资源 URL。
 *
 * Returns:
 *   浏览器可访问的完整地址。
 */
function buildImageUrl(relativeUrl) {
  if (!relativeUrl) {
    return ''
  }
  if (relativeUrl.startsWith('http')) {
    return relativeUrl
  }
  return `${backendOrigin}${relativeUrl}`
}

/**
 * 解析对象为表格展示数组。
 *
 * Args:
 *   source: 任意对象。
 *
 * Returns:
 *   键值对数组。
 */
function toKeyValueRows(source) {
  if (!source || typeof source !== 'object') {
    return []
  }
  return Object.entries(source).map(([key, value]) => ({
    key,
    value: typeof value === 'object' ? JSON.stringify(value) : String(value),
  }))
}

const gpcRows = computed(() => structuredData.value.analysis_results || [])
const nmrRows = computed(() => structuredData.value.nmr_results || [])

/**
 * 加载任务详情数据。
 *
 * Returns:
 *   Promise<void>
 */
async function fetchDetail() {
  loading.value = true
  try {
    const [status, result, artifacts] = await Promise.all([
      getTaskStatus(taskId.value),
      getTaskResult(taskId.value),
      getTaskArtifacts(taskId.value),
    ])
    statusData.value = status
    resultData.value = result
    artifactItems.value = artifacts.items || []
  } finally {
    loading.value = false
  }
}

/**
 * 判断当前任务是否成功结束。
 *
 * Returns:
 *   boolean
 */
function isSuccess() {
  return resultData.value?.status === 'SUCCESS'
}

onMounted(fetchDetail)
</script>

<template>
  <div class="page-grid">
    <div class="panel">
      <div class="panel-header">
        <h3 class="panel-title">任务详情</h3>
        <el-button type="primary" plain @click="fetchDetail">刷新</el-button>
      </div>
      <div class="panel-body" v-loading="loading">
        <el-descriptions v-if="statusData" :column="2" border>
          <el-descriptions-item label="任务ID">{{ statusData.task_id }}</el-descriptions-item>
          <el-descriptions-item label="任务类型">{{ statusData.task_type }}</el-descriptions-item>
          <el-descriptions-item label="任务状态">{{ statusData.status }}</el-descriptions-item>
          <el-descriptions-item label="当前消息">{{ statusData.message }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ statusData.created_at }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ statusData.updated_at }}</el-descriptions-item>
        </el-descriptions>

        <div style="margin-top: 14px">
          <el-progress v-if="statusData" :percentage="statusData.progress" :stroke-width="10" />
        </div>

        <el-divider />

        <el-alert
          v-if="resultData?.status === 'FAILED'"
          type="error"
          :closable="false"
          :title="resultData?.error?.error_message || '任务失败'"
          :description="resultData?.error?.error_detail"
        />

        <template v-if="isSuccess() && isGpcTask">
          <h4 style="margin: 8px 0">GPC 结果概览</h4>
          <el-table :data="gpcRows" stripe>
            <el-table-column prop="simple_name" label="样品简称" min-width="120" />
            <el-table-column prop="actual_curve_name" label="曲线名称" min-width="220" />
            <el-table-column label="分子量参数" min-width="280">
              <template #default="scope">
                <el-descriptions :column="1" size="small" border>
                  <el-descriptions-item
                    v-for="row in toKeyValueRows(scope.row.molecular_parameters)"
                    :key="row.key"
                    :label="row.key"
                  >
                    {{ row.value }}
                  </el-descriptions-item>
                </el-descriptions>
              </template>
            </el-table-column>
          </el-table>
        </template>

        <template v-if="isSuccess() && isNmrTask">
          <h4 style="margin: 8px 0">NMR 结果概览</h4>
          <el-table :data="nmrRows" stripe>
            <el-table-column prop="sample_name" label="样品名称" min-width="180" />
            <el-table-column label="积分结果" min-width="280">
              <template #default="scope">
                <el-descriptions :column="1" size="small" border>
                  <el-descriptions-item
                    v-for="row in toKeyValueRows(scope.row.integration_results)"
                    :key="row.key"
                    :label="row.key"
                  >
                    {{ row.value }}
                  </el-descriptions-item>
                </el-descriptions>
              </template>
            </el-table-column>
            <el-table-column label="归一化结果" min-width="280">
              <template #default="scope">
                <el-descriptions :column="1" size="small" border>
                  <el-descriptions-item
                    v-for="row in toKeyValueRows(scope.row.normalized_results)"
                    :key="row.key"
                    :label="row.key"
                  >
                    {{ row.value }}
                  </el-descriptions-item>
                </el-descriptions>
              </template>
            </el-table-column>
          </el-table>
        </template>

        <template v-if="imageArtifacts.length > 0">
          <el-divider />
          <h4 style="margin: 8px 0">分析图像产物</h4>
          <el-row :gutter="12">
            <el-col v-for="item in imageArtifacts" :key="item.relative_path" :xs="24" :sm="12" :lg="8" style="margin-bottom: 12px">
              <el-card shadow="hover">
                <template #header>
                  <div style="font-size: 13px; color: #3d5377; word-break: break-all">{{ item.name }}</div>
                </template>
                <el-image
                  :src="buildImageUrl(item.url)"
                  fit="contain"
                  style="width: 100%; height: 220px; background: #f6f9ff"
                  :preview-src-list="imageArtifacts.map((x) => buildImageUrl(x.url))"
                  :initial-index="imageArtifacts.findIndex((x) => x.relative_path === item.relative_path)"
                />
              </el-card>
            </el-col>
          </el-row>
        </template>

        <template v-if="isSuccess()">
          <el-divider />
          <h4 style="margin: 8px 0">文本报告</h4>
          <el-input :model-value="resultData?.result?.text_report || ''" type="textarea" :rows="12" readonly />
        </template>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <h3 class="panel-title">结构化结果（JSON）</h3>
      </div>
      <div class="panel-body">
        <pre class="json-block">{{ JSON.stringify(structuredData, null, 2) }}</pre>
      </div>
    </div>
  </div>
</template>
