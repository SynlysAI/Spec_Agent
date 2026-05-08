const AUTH_STORAGE_KEY = 'spec_agent_auth_session'

/**
 * 读取本地会话信息。
 *
 * Returns:
 *   当前已保存的登录会话；不存在时返回 null。
 */
export function getStoredAuthSession() {
  if (typeof window === 'undefined') {
    return null
  }
  const raw = window.sessionStorage.getItem(AUTH_STORAGE_KEY)
  if (!raw) {
    return null
  }
  try {
    const session = JSON.parse(raw)
    if (!session?.accessToken || !session?.tokenType) {
      return null
    }
    return session
  } catch {
    return null
  }
}

/**
 * 保存登录会话信息。
 *
 * Args:
 *   session: 待保存的会话对象。
 */
export function setStoredAuthSession(session) {
  if (typeof window === 'undefined') {
    return
  }
  window.sessionStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session))
}

/**
 * 清理登录会话信息。
 */
export function clearStoredAuthSession() {
  if (typeof window === 'undefined') {
    return
  }
  window.sessionStorage.removeItem(AUTH_STORAGE_KEY)
}

/**
 * 判断当前会话是否仍在有效期内。
 *
 * Args:
 *   session: 会话对象。
 *
 * Returns:
 *   是否有效。
 */
export function isAuthSessionValid(session) {
  if (!session?.accessToken || !session?.expiresAt) {
    return false
  }
  return Number(session.expiresAt) * 1000 > Date.now()
}
