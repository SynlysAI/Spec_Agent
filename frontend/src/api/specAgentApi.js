import axios from 'axios'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1',
  timeout: 60000,
})

function unwrapResponse(response) {
  const payload = response.data || {}
  if (payload.code !== 0) {
    throw new Error(payload.message || '请求失败')
  }
  return payload.data
}

/**
 * 解析 Axios 异常并提取可读错误信息。
 *
 * Args:
 *   error: Axios 抛出的异常对象。
 *
 * Returns:
 *   适合界面提示的错误字符串。
 */
export function getApiErrorMessage(error) {
  const responseData = error?.response?.data
  if (responseData?.message) {
    const detail = responseData?.data?.detail
    if (detail) {
      return `${responseData.message}: ${detail}`
    }
    const firstValidationError = responseData?.data?.errors?.[0]?.msg
    if (firstValidationError) {
      return `${responseData.message}: ${firstValidationError}`
    }
    return responseData.message
  }
  if (error?.message) {
    return error.message
  }
  return '请求失败'
}

export async function listTasks(params) {
  const response = await apiClient.get('/tasks', { params })
  return unwrapResponse(response)
}

export async function createGpcTask(payload) {
  const response = await apiClient.post('/tasks/gpc', payload)
  return unwrapResponse(response)
}

export async function createNmrTask(payload) {
  const response = await apiClient.post('/tasks/nmr', payload)
  return unwrapResponse(response)
}

export async function getTaskStatus(taskId) {
  const response = await apiClient.get(`/tasks/${taskId}`)
  return unwrapResponse(response)
}

export async function getTaskResult(taskId) {
  const response = await apiClient.get(`/tasks/${taskId}/result`)
  return unwrapResponse(response)
}

/**
 * 查询任务产物列表。
 *
 * Args:
 *   taskId: 任务 ID。
 *
 * Returns:
 *   任务产物对象。
 */
export async function getTaskArtifacts(taskId) {
  const response = await apiClient.get(`/tasks/${taskId}/artifacts`)
  return unwrapResponse(response)
}

export async function uploadFile(file, bizType) {
  const formData = new FormData()
  formData.append('file', file)
  if (bizType) {
    formData.append('biz_type', bizType)
  }
  const response = await apiClient.post('/files/upload', formData)
  return unwrapResponse(response)
}
