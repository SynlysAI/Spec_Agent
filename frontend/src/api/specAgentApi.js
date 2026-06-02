import axios from 'axios'

import { clearAuthSession, getAuthorizationHeader } from '../auth/authState'

/**
 * 生成默认 API 基础地址。
 *
 * Returns:
 *   默认 API 基础地址。
 */
function resolveDefaultApiBaseUrl() {
  return '/api/v1'
}

const DEFAULT_API_BASE_URL = resolveDefaultApiBaseUrl()
const REQUEST_TIMEOUT_MS = 60000

/**
 * 生成请求追踪 ID。
 *
 * Returns:
 *   可用于 X-Request-Id 请求头的追踪字符串。
 */
function generateRequestId() {
  return `${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
}

/**
 * 解析并归一化 API 基础地址。
 *
 * Returns:
 *   规范化后的 API 基础地址。
 */
function resolveApiBaseUrl() {
  const rawBaseUrl = String(import.meta.env.VITE_API_BASE_URL || '').trim()
  if (!rawBaseUrl) {
    return DEFAULT_API_BASE_URL
  }
  return rawBaseUrl.replace(/\/+$/, '')
}

const resolvedBaseUrl = resolveApiBaseUrl()

const AUTH_EXPIRED_EVENT_NAME = 'spec-agent-auth-expired'

const apiClient = axios.create({
  baseURL: resolvedBaseUrl,
  timeout: REQUEST_TIMEOUT_MS,
})

/**
 * 通知前端登录态已失效。
 */
function notifyAuthExpired() {
  if (typeof window === 'undefined') {
    return
  }
  window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT_NAME))
}

/**
 * 创建标准化 API 错误对象。
 *
 * Args:
 *   options: 错误对象构造参数。
 *
 * Returns:
 *   统一格式的错误对象。
 */
function createApiError(options) {
  const error = new Error(options.message || '请求失败')
  error.name = 'ApiError'
  error.kind = options.kind || 'unknown'
  error.code = options.code ?? null
  error.status = options.status ?? null
  error.requestId = options.requestId || null
  error.detail = options.detail || null
  error.path = options.path || null
  error.errors = Array.isArray(options.errors) ? options.errors : null
  error.original = options.original || null
  return error
}

/**
 * 统一解包后端响应。
 *
 * Args:
 *   response: Axios 响应对象。
 *
 * Returns:
 *   业务响应 data。
 */
function unwrapResponse(response) {
  const payload = response?.data || {}
  if (payload.code !== 0) {
    throw createApiError({
      kind: 'api_business',
      message: payload.message || '请求失败',
      code: payload.code,
      status: response?.status || null,
      requestId: payload.request_id || response?.headers?.['x-request-id'] || null,
      detail: payload?.data?.detail || null,
      path: payload?.data?.path || null,
      errors: payload?.data?.errors || null,
      original: payload,
    })
  }
  return payload.data
}

apiClient.interceptors.request.use((config) => {
  const requestId = generateRequestId()
  const headers = config.headers || {}
  headers['X-Request-Id'] = requestId
  const authorization = getAuthorizationHeader()
  if (authorization) {
    headers.Authorization = authorization
  } else {
    delete headers.Authorization
  }
  config.headers = headers
  config.metadata = {
    ...(config.metadata || {}),
    requestId,
    startedAt: Date.now(),
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.name === 'CanceledError') {
      return Promise.reject(
        createApiError({
          kind: 'canceled',
          message: '请求已取消',
          original: error,
        }),
      )
    }

    const responseData = error?.response?.data || {}
    const responseStatus = error?.response?.status || null
    const requestId =
      responseData?.request_id ||
      error?.response?.headers?.['x-request-id'] ||
      error?.config?.metadata?.requestId ||
      null

    if (!error?.response) {
      if (error?.code === 'ECONNABORTED') {
        return Promise.reject(
          createApiError({
            kind: 'timeout',
            message: '请求超时，请稍后重试',
            requestId,
            original: error,
          }),
        )
      }
      return Promise.reject(
        createApiError({
          kind: 'network',
          message: '网络异常，请检查网络连接',
          requestId,
          original: error,
        }),
      )
    }

    if (responseStatus === 401) {
      clearAuthSession()
      notifyAuthExpired()
    }

    const apiMessage = responseData?.message || '请求失败'
    return Promise.reject(
      createApiError({
        kind: 'http',
        message: apiMessage,
        code: responseData?.code ?? null,
        status: responseStatus,
        requestId,
        detail: responseData?.data?.detail || null,
        path: responseData?.data?.path || null,
        errors: responseData?.data?.errors || null,
        original: error,
      }),
    )
  },
)

/**
 * 解析 API 异常并提取可读错误信息。
 *
 * Args:
 *   error: API 抛出的异常对象。
 *
 * Returns:
 *   适合界面提示的错误字符串。
 */
export function getApiErrorMessage(error) {
  if (!error) {
    return '请求失败'
  }

  if (error.kind === 'canceled') {
    return '请求已取消'
  }
  if (error.kind === 'timeout') {
    return '请求超时，请稍后重试'
  }
  if (error.kind === 'network') {
    return '网络异常，请检查网络连接'
  }

  const firstValidationError = error?.errors?.[0]?.msg
  if (firstValidationError) {
    return `${error.message}: ${firstValidationError}`
  }

  if (error?.detail) {
    return `${error.message}: ${error.detail}`
  }

  if (typeof error.message === 'string' && error.message.trim()) {
    return error.message
  }
  return '请求失败'
}

/**
 * 判断错误是否属于请求取消。
 *
 * Args:
 *   error: 待判断的异常对象。
 *
 * Returns:
 *   是否为取消请求异常。
 */
export function isRequestCanceled(error) {
  return error?.kind === 'canceled'
}

/**
 * 获取 API 基础地址。
 *
 * Returns:
 *   规范化后的 API 基础地址。
 */
export function getApiBaseUrl() {
  return resolvedBaseUrl
}

/**
 * 构建浏览器可直接访问的绝对 API 地址。
 *
 * Args:
 *   path: 以 `/` 开头的 API 相对路径。
 *
 * Returns:
 *   绝对 API 地址字符串。
 */
export function buildAbsoluteApiUrl(path) {
  const normalizedBase = String(resolvedBaseUrl || '').replace(/\/+$/, '')
  return new URL(`${normalizedBase}${path}`, window.location.origin).toString()
}

/**
 * 获取静态产物基础地址。
 *
 * Returns:
 *   不带 `/api/v1` 的服务基础地址。
 */
export function getStaticBaseUrl() {
  return resolvedBaseUrl.replace(/\/api\/v1\/?$/, '')
}

/**
 * 通过鉴权请求获取图片 Blob。
 *
 * Args:
 *   url: 图片接口完整地址或相对地址。
 *
 * Returns:
 *   图片 Blob 数据。
 */
export async function fetchProtectedImageBlob(url, options = {}) {
  const response = await apiClient.get(url, {
    ...buildRequestConfig(options),
    responseType: 'blob',
  })
  const contentType = String(response?.headers?.['content-type'] || '').toLowerCase()
  if (!contentType.startsWith('image/')) {
    throw createApiError({
      kind: 'invalid_content_type',
      message: '接口未返回有效图片数据',
      status: response?.status || null,
      requestId: response?.headers?.['x-request-id'] || null,
      detail: contentType || 'unknown content-type',
      original: response,
    })
  }
  return response.data
}

/**
 * 下载受保护接口返回的文件 Blob。
 *
 * Args:
 *   url: 文件接口完整地址或相对地址。
 *
 * Returns:
 *   包含 Blob、文件名与内容类型的结果对象。
 */
export async function fetchProtectedFileBlob(url, options = {}) {
  const response = await apiClient.get(url, {
    ...buildRequestConfig(options),
    responseType: 'blob',
  })
  const contentType = String(response?.headers?.['content-type'] || '').toLowerCase()
  if (contentType.includes('text/html')) {
    throw createApiError({
      kind: 'invalid_content_type',
      message: '接口未返回有效文件数据',
      status: response?.status || null,
      requestId: response?.headers?.['x-request-id'] || null,
      detail: contentType,
      original: response,
    })
  }

  const contentDisposition = String(response?.headers?.['content-disposition'] || '')
  const fileNameMatch =
    contentDisposition.match(/filename\*=UTF-8''([^;]+)/i) ||
    contentDisposition.match(/filename=\"?([^\";]+)\"?/i)
  const fileName = fileNameMatch?.[1] ? decodeURIComponent(fileNameMatch[1]) : ''

  return {
    blob: response.data,
    contentType,
    fileName,
  }
}

/**
 * 生成 HTTP 请求配置对象。
 *
 * Args:
 *   options: 传输层配置。
 *
 * Returns:
 *   Axios 请求配置。
 */
function buildRequestConfig(options = {}) {
  const config = {}
  if (options.params) {
    config.params = options.params
  }
  if (options.signal) {
    config.signal = options.signal
  }
  if (options.timeout) {
    config.timeout = options.timeout
  }
  return config
}

/**
 * 查询服务端登录开关与当前登录状态。
 *
 * Returns:
 *   鉴权状态对象。
 */
export async function getAuthStatus(options = {}) {
  const response = await apiClient.get('/auth/status', buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 使用账号密码进行登录。
 *
 * Args:
 *   payload: 登录参数。
 *
 * Returns:
 *   登录结果对象。
 */
export async function loginWithPassword(payload, options = {}) {
  const response = await apiClient.post('/auth/login', payload, buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 使用邀请码执行注册。
 *
 * Args:
 *   payload: 注册参数。
 *
 * Returns:
 *   当前注册用户信息。
 */
export async function registerWithInviteCode(payload, options = {}) {
  const response = await apiClient.post('/auth/register', payload, buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 获取当前登录用户信息。
 *
 * Returns:
 *   当前用户态信息。
 */
export async function getCurrentUser(options = {}) {
  const response = await apiClient.get('/auth/me', buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 查询管理员用户列表。
 *
 * Returns:
 *   管理员用户列表数据。
 */
export async function listAdminUsers(options = {}) {
  const response = await apiClient.get('/admin/users', buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 更新指定用户状态。
 *
 * Args:
 *   userId: 目标用户 ID。
 *   payload: 状态更新参数。
 *
 * Returns:
 *   更新后的用户状态数据。
 */
export async function updateAdminUserStatus(userId, payload, options = {}) {
  const response = await apiClient.patch(`/admin/users/${userId}/status`, payload, buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 查询管理员邀请码列表。
 *
 * Returns:
 *   邀请码列表数据。
 */
export async function listInviteCodes(options = {}) {
  const response = await apiClient.get('/admin/invite-codes', buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 创建邀请码。
 *
 * Args:
 *   payload: 邀请码创建参数。
 *
 * Returns:
 *   新建邀请码数据。
 */
export async function createInviteCode(payload, options = {}) {
  const response = await apiClient.post('/admin/invite-codes', payload, buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 禁用指定邀请码。
 *
 * Args:
 *   inviteId: 目标邀请码 ID。
 *
 * Returns:
 *   更新后的邀请码状态数据。
 */
export async function disableInviteCode(inviteId, options = {}) {
  const response = await apiClient.patch(
    `/admin/invite-codes/${inviteId}/disable`,
    null,
    buildRequestConfig(options),
  )
  return unwrapResponse(response)
}

export async function listTasks(params, options = {}) {
  const response = await apiClient.get('/tasks', buildRequestConfig({ params, ...options }))
  return unwrapResponse(response)
}

export async function createGpcTask(payload, options = {}) {
  const response = await apiClient.post('/tasks/gpc', payload, buildRequestConfig(options))
  return unwrapResponse(response)
}

export async function createNmrTask(payload, options = {}) {
  const response = await apiClient.post('/tasks/nmr', payload, buildRequestConfig(options))
  return unwrapResponse(response)
}

export async function createIrTask(payload, options = {}) {
  const response = await apiClient.post('/tasks/ir', payload, buildRequestConfig(options))
  return unwrapResponse(response)
}

export async function createRamanTask(payload, options = {}) {
  const response = await apiClient.post('/tasks/raman', payload, buildRequestConfig(options))
  return unwrapResponse(response)
}

export async function createLcmsTask(payload, options = {}) {
  const response = await apiClient.post('/tasks/lcms', payload, buildRequestConfig(options))
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
export async function previewSpectrum(formData, options = {}) {
  const response = await apiClient.post('/spectra/preview', formData, buildRequestConfig(options))
  return unwrapResponse(response)
}

export async function nmrserverForward(payload, options = {}) {
  const response = await apiClient.post('/nmrserver/forward', payload, buildRequestConfig(options))
  return unwrapResponse(response)
}

export async function nmrserverReverse(payload, options = {}) {
  const response = await apiClient.post('/nmrserver/reverse', payload, buildRequestConfig(options))
  return unwrapResponse(response)
}

export async function nmrserverSearch(payload, options = {}) {
  const response = await apiClient.post('/nmrserver/search', payload, buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 执行拉曼光谱仪批量采集。
 *
 * Args:
 *   payload: 拉曼采集参数。
 *
 * Returns:
 *   批量采集报告数据。
 */
export async function runRamanCapture(payload, options = {}) {
  const response = await apiClient.post('/raman-capture/run', payload, buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 拉曼光谱仪自动对焦。
 *
 * Args:
 *   payload: 对焦参数（rt, rb, s）。
 *
 * Returns:
 *   对焦结果信息。
 */
export async function focusRamanCamera(payload, options = {}) {
  const response = await apiClient.post('/raman-capture/focus', payload, buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 执行 LCMS 数据目录转化。
 *
 * Args:
 *   formData: 包含 zip 文件的表单数据。
 *
 * Returns:
 *   LCMS 转化结果对象。
 */
export async function runLcmsConvert(formData, options = {}) {
  const response = await apiClient.post('/tools/lcms-convert/run', formData, buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 构建 LCMS 转化结果下载地址。
 *
 * Args:
 *   jobId: 转化任务 ID。
 *
 * Returns:
 *   可直接下载的绝对 URL。
 */
export function buildLcmsConvertDownloadUrl(jobId) {
  return buildAbsoluteApiUrl(`/tools/lcms-convert/download/${encodeURIComponent(jobId)}`)
}

export async function getTaskStatus(taskId, options = {}) {
  const response = await apiClient.get(`/tasks/${taskId}`, buildRequestConfig(options))
  return unwrapResponse(response)
}

export async function getTaskResult(taskId, options = {}) {
  const response = await apiClient.get(`/tasks/${taskId}/result`, buildRequestConfig(options))
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
export async function getTaskArtifacts(taskId, options = {}) {
  const response = await apiClient.get(`/tasks/${taskId}/artifacts`, buildRequestConfig(options))
  return unwrapResponse(response)
}

export async function uploadFile(file, bizType, options = {}) {
  const formData = new FormData()
  formData.append('file', file)
  if (bizType) {
    formData.append('biz_type', bizType)
  }
  const response = await apiClient.post('/files/upload', formData, buildRequestConfig(options))
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
export async function listDialogueAnalysisTypes(options = {}) {
  const response = await apiClient.get('/dialogue/analysis-types', buildRequestConfig(options))
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
export async function listDialogueReports(analysisType, options = {}) {
  const response = await apiClient.get('/dialogue/reports', {
    ...buildRequestConfig(options),
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
export async function dialogueChat(payload, options = {}) {
  const response = await apiClient.post('/dialogue/chat', payload, buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 查询验收配置摘要。
 *
 * Returns:
 *   验收配置数据。
 */
export async function getAcceptanceConfig(options = {}) {
  const response = await apiClient.get('/acceptance/config', buildRequestConfig(options))
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
export async function createAcceptanceRun(spectrumTypes, options = {}) {
  const response = await apiClient.post(
    '/acceptance/run',
    {
      spectrum_types: spectrumTypes,
    },
    buildRequestConfig(options),
  )
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
export async function getAcceptanceRun(runId, options = {}) {
  const response = await apiClient.get(`/acceptance/run/${runId}`, buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 查询批量验收历史列表。
 *
 * Args:
 *   limit: 返回条数上限。
 *
 * Returns:
 *   历史批次列表数据。
 */
export async function getAcceptanceRuns(limit = 20, options = {}) {
  const response = await apiClient.get('/acceptance/runs', {
    ...buildRequestConfig(options),
    params: { limit },
  })
  return unwrapResponse(response)
}

/**
 * 查询设备重复性评测配置摘要。
 *
 * Returns:
 *   一致性评测配置数据。
 */
export async function getConsistencyConfig(options = {}) {
  const response = await apiClient.get('/consistency/config', buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 启动设备重复性评测运行。
 *
 * Args:
 *   deviceTypes: 设备类型列表，为空表示全量。
 *
 * Returns:
 *   运行创建结果。
 */
export async function createConsistencyRun(deviceTypes, options = {}) {
  const response = await apiClient.post(
    '/consistency/run',
    {
      device_types: deviceTypes,
    },
    buildRequestConfig(options),
  )
  return unwrapResponse(response)
}

/**
 * 查询设备重复性评测运行状态。
 *
 * Args:
 *   runId: 批次运行 ID。
 *
 * Returns:
 *   批次运行数据。
 */
export async function getConsistencyRun(runId, options = {}) {
  const response = await apiClient.get(`/consistency/run/${runId}`, buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 查询设备重复性评测历史列表。
 *
 * Args:
 *   limit: 返回条数上限。
 *
 * Returns:
 *   历史批次列表数据。
 */
export async function getConsistencyRuns(limit = 20, options = {}) {
  const response = await apiClient.get('/consistency/runs', {
    ...buildRequestConfig(options),
    params: { limit },
  })
  return unwrapResponse(response)
}

/**
 * 查询实验室采集配置摘要。
 *
 * Returns:
 *   采集配置数据。
 */
export async function getLabCollectConfig(options = {}) {
  const response = await apiClient.get('/lab-collect/config', buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 创建实验室数据采集批次。
 *
 * Args:
 *   payload: 采集请求参数。
 *
 * Returns:
 *   批次创建结果。
 */
export async function createLabCollectRun(payload, options = {}) {
  const response = await apiClient.post('/lab-collect/run', payload, buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 查询实验室数据采集历史。
 *
 * Args:
 *   limit: 返回条数。
 *
 * Returns:
 *   采集批次列表。
 */
export async function getLabCollectRuns(limit = 20, options = {}) {
  const response = await apiClient.get('/lab-collect/runs', {
    ...buildRequestConfig(options),
    params: { limit },
  })
  return unwrapResponse(response)
}

/**
 * 查询实验室采集批次详情。
 *
 * Args:
 *   runId: 批次 ID。
 *
 * Returns:
 *   批次详情。
 */
export async function getLabCollectRun(runId, options = {}) {
  const response = await apiClient.get(`/lab-collect/run/${runId}`, buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 查询实验样本汇总。
 *
 * Returns:
 *   样本汇总数据。
 */
export async function getSpectrumSampleSummary(options = {}) {
  const response = await apiClient.get('/lab-collect/samples/summary', buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 查询分子资产统计缓存。
 *
 * Returns:
 *   分子统计结果。
 */
export async function getMolecularStatistics(options = {}) {
  const response = await apiClient.get('/lab-collect/molecular-stats', buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 手动刷新分子资产统计缓存。
 *
 * Returns:
 *   刷新后的分子统计结果。
 */
export async function refreshMolecularStatistics(options = {}) {
  const response = await apiClient.post('/lab-collect/molecular-stats/refresh', {}, buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 分页查询实验样本主档。
 *
 * Args:
 *   params: 查询参数。
 *
 * Returns:
 *   样本分页结果。
 */
export async function listSpectrumSamples(params, options = {}) {
  const response = await apiClient.get('/lab-collect/samples', {
    ...buildRequestConfig(options),
    params,
  })
  return unwrapResponse(response)
}

/**
 * 查询实验样本详情。
 *
 * Args:
 *   sampleId: 样本 ID。
 *
 * Returns:
 *   样本详情对象。
 */
export async function getSpectrumSampleDetail(sampleId, options = {}) {
  const response = await apiClient.get(`/lab-collect/samples/${sampleId}`, buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 删除实验样本。
 *
 * Args:
 *   sampleId: 样本 ID。
 *
 * Returns:
 *   删除结果。
 */
export async function deleteSpectrumSample(sampleId, options = {}) {
  const response = await apiClient.delete(`/lab-collect/samples/${sampleId}`, buildRequestConfig(options))
  return unwrapResponse(response)
}

/**
 * 构建批量验收报告下载地址。
 *
 * Args:
 *   runId: 批次运行 ID。
 *
 * Returns:
 *   可直接打开下载的 URL。
 */
export function buildAcceptanceReportUrl(runId) {
  return buildAbsoluteApiUrl(`/acceptance/run/${runId}/report`)
}

/**
 * 构建设备重复性评测报告下载地址。
 *
 * Args:
 *   runId: 批次运行 ID。
 *
 * Returns:
 *   可直接打开下载的 URL。
 */
export function buildConsistencyReportUrl(runId) {
  return buildAbsoluteApiUrl(`/consistency/run/${runId}/report`)
}
