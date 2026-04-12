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

export async function createIrTask(payload) {
  const response = await apiClient.post('/tasks/ir', payload)
  return unwrapResponse(response)
}

export async function createRamanTask(payload) {
  const response = await apiClient.post('/tasks/raman', payload)
  return unwrapResponse(response)
}

/**
 * 预览谱图数据。
 *
 * Args:
 *   formData: 谱图预览请求表单。
 *
 * Returns:
 *   谱图预览结果对象。
 */
export async function previewSpectrum(formData) {
  const response = await apiClient.post('/spectra/preview', formData)
  return unwrapResponse(response)
}

export async function nmrserverForward(payload) {
  const response = await apiClient.post('/nmrserver/forward', payload)
  return unwrapResponse(response)
}

export async function nmrserverReverse(payload) {
  const response = await apiClient.post('/nmrserver/reverse', payload)
  return unwrapResponse(response)
}

export async function nmrserverSearch(payload) {
  const response = await apiClient.post('/nmrserver/search', payload)
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
  const data = unwrapResponse(response)
  const normalizedFileName = data?.file_name || data?.filename || ''
  return {
    ...data,
    file_name: normalizedFileName,
    filename: normalizedFileName,
  }
}

/**
 * 查询问答分析类型列表。
 *
 * Returns:
 *   分析类型列表数据。
 */
export async function listDialogueAnalysisTypes() {
  const response = await apiClient.get('/dialogue/analysis-types')
  return unwrapResponse(response)
}

/**
 * 查询问答报告列表。
 *
 * Args:
 *   analysisType: 分析类型编码。
 *
 * Returns:
 *   报告列表数据。
 */
export async function listDialogueReports(analysisType) {
  const response = await apiClient.get('/dialogue/reports', {
    params: { analysis_type: analysisType, limit: 30 },
  })
  return unwrapResponse(response)
}

/**
 * 执行问答请求。
 *
 * Args:
 *   payload: 问答请求参数。
 *
 * Returns:
 *   问答响应数据。
 */
export async function dialogueChat(payload) {
  const response = await apiClient.post('/dialogue/chat', payload)
  return unwrapResponse(response)
}

/**
 * 查询验收配置摘要。
 *
 * Returns:
 *   验收配置数据。
 */
export async function getAcceptanceConfig() {
  const response = await apiClient.get('/acceptance/config')
  return unwrapResponse(response)
}

/**
 * 启动批量验收运行。
 *
 * Args:
 *   spectrumTypes: 谱图类型列表，为空表示全量。
 *
 * Returns:
 *   运行创建结果。
 */
export async function createAcceptanceRun(spectrumTypes) {
  const response = await apiClient.post('/acceptance/run', {
    spectrum_types: spectrumTypes,
  })
  return unwrapResponse(response)
}

/**
 * 查询批量验收运行状态。
 *
 * Args:
 *   runId: 批次运行 ID。
 *
 * Returns:
 *   批次运行数据。
 */
export async function getAcceptanceRun(runId) {
  const response = await apiClient.get(`/acceptance/run/${runId}`)
  return unwrapResponse(response)
}
