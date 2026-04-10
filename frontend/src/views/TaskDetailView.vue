<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getTaskResult, getTaskStatus } from '../api/specAgentApi'

const route = useRoute()
const taskId = computed(() => route.params.taskId)

const loading = ref(false)
const statusData = ref(null)
const resultData = ref(null)

/**
 * 加载任务详情数据。
 *
 * Returns:
 *   Promise<void>
 */
async function fetchDetail() {
  loading.value = true
  try {
    const status = await getTaskStatus(taskId.value)
    statusData.value = status
    const result = await getTaskResult(taskId.value)
    resultData.value = result
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

        <template v-if="isSuccess()">
          <h4 style="margin: 8px 0">文本报告</h4>
          <el-input :model-value="resultData?.result?.text_report || ''" type="textarea" :rows="12" readonly />
        </template>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <h3 class="panel-title">结构化结果</h3>
      </div>
      <div class="panel-body">
        <pre class="json-block">{{ JSON.stringify(resultData?.result?.structured_data || {}, null, 2) }}</pre>
      </div>
    </div>
  </div>
</template>
