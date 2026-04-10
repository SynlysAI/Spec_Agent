import axios from 'axios'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1',
  timeout: 60000,
})

/**
 * 统一解析后端响应。
 *
 * Args:
 *   response: Axios 原始响应对象。
 *
 * Returns:
 *   业务层可直接使用的数据对象。
 */
function unwrapResponse(response) {
  const payload = response.data || {}
  if (payload.code !== 0) {
    throw new Error(payload.message || '请求失败')
  }
  return payload.data
}

/**
 * 查询任务列表。
 *
 * Args:
 *   params: 查询参数（page/page_size/status/task_type）。
 *
 * Returns:
 *   任务分页数据。
 */
export async function listTasks(params) {
  const response = await apiClient.get('/tasks', { params })
  return unwrapResponse(response)
}

/**
 * 创建 GPC 任务。
 *
 * Args:
 *   payload: GPC 任务创建参数。
 *
 * Returns:
 *   任务基础信息。
 */
export async function createGpcTask(payload) {
  const response = await apiClient.post('/tasks/gpc', payload)
  return unwrapResponse(response)
}

/**
 * 创建 NMR 任务。
 *
 * Args:
 *   payload: NMR 任务创建参数。
 *
 * Returns:
 *   任务基础信息。
 */
export async function createNmrTask(payload) {
  const response = await apiClient.post('/tasks/nmr', payload)
  return unwrapResponse(response)
}

/**
 * 查询任务状态。
 *
 * Args:
 *   taskId: 任务 ID。
 *
 * Returns:
 *   任务状态对象。
 */
export async function getTaskStatus(taskId) {
  const response = await apiClient.get(`/tasks/${taskId}`)
  return unwrapResponse(response)
}

/**
 * 查询任务结果。
 *
 * Args:
 *   taskId: 任务 ID。
 *
 * Returns:
 *   任务结果对象。
 */
export async function getTaskResult(taskId) {
  const response = await apiClient.get(`/tasks/${taskId}/result`)
  return unwrapResponse(response)
}

/**
 * 上传文件。
 *
 * Args:
 *   file: 浏览器上传文件对象。
 *   bizType: 业务类型（gpc/nmr）。
 *
 * Returns:
 *   文件元数据。
 */
export async function uploadFile(file, bizType) {
  const formData = new FormData()
  formData.append('file', file)
  if (bizType) {
    formData.append('biz_type', bizType)
  }
  const response = await apiClient.post('/files/upload', formData)
  return unwrapResponse(response)
}
