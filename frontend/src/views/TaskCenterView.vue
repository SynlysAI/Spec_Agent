<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listTasks } from '../api/specAgentApi'

const router = useRouter()
const loading = ref(false)
const tableData = ref([])

const query = reactive({
  page: 1,
  page_size: 10,
  status: '',
  task_type: '',
})

const pagination = reactive({
  total: 0,
  page: 1,
  page_size: 10,
})

/**
 * 查询任务列表数据。
 *
 * Returns:
 *   Promise<void>
 */
async function fetchTasks() {
  loading.value = true
  try {
    const params = {
      page: query.page,
      page_size: query.page_size,
      status: query.status || undefined,
      task_type: query.task_type || undefined,
    }
    const data = await listTasks(params)
    tableData.value = data.items || []
    pagination.total = data.total
    pagination.page = data.page
    pagination.page_size = data.page_size
  } finally {
    loading.value = false
  }
}

/**
 * 跳转任务详情页。
 *
 * Args:
 *   taskId: 任务 ID。
 */
function goDetail(taskId) {
  router.push(`/tasks/detail/${taskId}`)
}

/**
 * 处理筛选条件重置。
 */
function resetFilters() {
  query.status = ''
  query.task_type = ''
  query.page = 1
  fetchTasks()
}

onMounted(fetchTasks)
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <h3 class="panel-title">任务中心</h3>
      <div>
        <el-button @click="resetFilters">重置</el-button>
        <el-button type="primary" plain @click="fetchTasks">刷新</el-button>
      </div>
    </div>
    <div class="panel-body">
      <el-form :inline="true">
        <el-form-item label="状态">
          <el-select v-model="query.status" placeholder="全部" style="width: 140px" @change="query.page = 1; fetchTasks()">
            <el-option label="全部" value="" />
            <el-option label="PENDING" value="PENDING" />
            <el-option label="QUEUED" value="QUEUED" />
            <el-option label="RUNNING" value="RUNNING" />
            <el-option label="SUCCESS" value="SUCCESS" />
            <el-option label="FAILED" value="FAILED" />
          </el-select>
        </el-form-item>
        <el-form-item label="任务类型">
          <el-select v-model="query.task_type" placeholder="全部" style="width: 180px" @change="query.page = 1; fetchTasks()">
            <el-option label="全部" value="" />
            <el-option label="gpc_analysis" value="gpc_analysis" />
            <el-option label="nmr_analysis" value="nmr_analysis" />
          </el-select>
        </el-form-item>
      </el-form>

      <el-table :data="tableData" v-loading="loading" stripe>
        <el-table-column prop="task_id" label="任务ID" min-width="280" />
        <el-table-column prop="task_type" label="类型" width="140" />
        <el-table-column prop="status" label="状态" width="110" />
        <el-table-column prop="progress" label="进度" width="110">
          <template #default="scope">
            <el-progress :percentage="scope.row.progress" :stroke-width="8" />
          </template>
        </el-table-column>
        <el-table-column prop="message" label="消息" min-width="160" />
        <el-table-column prop="updated_at" label="更新时间" min-width="190" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="scope">
            <el-button type="primary" link @click="goDetail(scope.row.task_id)">查看</el-button>
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
          @current-change="fetchTasks"
          @size-change="query.page = 1; fetchTasks()"
        />
      </div>
    </div>
  </div>
</template>
