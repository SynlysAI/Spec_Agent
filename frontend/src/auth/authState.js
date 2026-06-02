import { reactive } from 'vue'

import {
  clearStoredAuthSession,
  getStoredAuthSession,
  isAuthSessionValid,
  setStoredAuthSession,
} from './authStorage'

const initialSession = getStoredAuthSession()
const hasValidInitialSession = isAuthSessionValid(initialSession)

export const authState = reactive({
  initialized: false,
  authEnabled: false,
  authenticated: hasValidInitialSession,
  userId: hasValidInitialSession ? initialSession.userId || '' : '',
  username: hasValidInitialSession ? initialSession.username || '' : '',
  role: hasValidInitialSession ? initialSession.role || '' : '',
  status: hasValidInitialSession ? initialSession.status || '' : '',
  tokenType: hasValidInitialSession ? initialSession.tokenType || 'Bearer' : 'Bearer',
  accessToken: hasValidInitialSession ? initialSession.accessToken || '' : '',
  expiresAt: hasValidInitialSession ? initialSession.expiresAt || 0 : 0,
})

/**
 * 更新服务端鉴权开关状态。
 *
 * Args:
 *   enabled: 后端是否启用登录校验。
 */
export function setAuthEnabled(enabled) {
  authState.authEnabled = Boolean(enabled)
  authState.initialized = true
  if (!authState.authEnabled) {
    clearAuthSession()
  }
}

/**
 * 写入新的登录会话。
 *
 * Args:
 *   session: 登录会话信息。
 */
export function setAuthSession(session) {
  authState.authenticated = true
  authState.userId = session.userId || ''
  authState.username = session.username || ''
  authState.role = session.role || ''
  authState.status = session.status || ''
  authState.tokenType = session.tokenType || 'Bearer'
  authState.accessToken = session.accessToken || ''
  authState.expiresAt = session.expiresAt || 0
  setStoredAuthSession({
    userId: authState.userId,
    username: authState.username,
    role: authState.role,
    status: authState.status,
    tokenType: authState.tokenType,
    accessToken: authState.accessToken,
    expiresAt: authState.expiresAt,
  })
}

/**
 * 清空当前登录会话。
 */
export function clearAuthSession() {
  authState.authenticated = false
  authState.userId = ''
  authState.username = ''
  authState.role = ''
  authState.status = ''
  authState.tokenType = 'Bearer'
  authState.accessToken = ''
  authState.expiresAt = 0
  clearStoredAuthSession()
}

/**
 * 获取可用于请求头的 Authorization 值。
 *
 * Returns:
 *   Authorization 请求头值；无可用会话时返回空字符串。
 */
export function getAuthorizationHeader() {
  if (!authState.authenticated) {
    return ''
  }
  if (!isAuthSessionValid(authState)) {
    clearAuthSession()
    return ''
  }
  return `${authState.tokenType} ${authState.accessToken}`
}
