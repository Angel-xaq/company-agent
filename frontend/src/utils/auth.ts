// 存储 token / 用户信息 / 菜单 / 权限；登出钩子供 UserContext 清理内存态
import type { MenuNode, UserInfo } from '@/types'

export const TOKEN_KEY = 'token'
export const USER_KEY = 'userInfo'
export const MENUS_KEY = 'menus'
export const PERMS_KEY = 'permissions'

let logoutHandler: (() => void) | null = null

/** 由 UserContext 注册，用于清空菜单/权限内存态（避免循环依赖） */
export function onLogout(fn: () => void) {
  logoutHandler = fn
}

/** 安全解析 localStorage 中的 JSON */
export function readJson<T>(key: string): T | null {
  try {
    const str = localStorage.getItem(key)
    return str ? (JSON.parse(str) as T) : null
  } catch {
    return null
  }
}

/** 将值序列化写入 localStorage */
export function writeJson(key: string, value: unknown) {
  localStorage.setItem(key, JSON.stringify(value))
}

/** 读取本地 token */
export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

/** 写入本地 token */
export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
}

/** 清除本地 token */
export function removeToken() {
  localStorage.removeItem(TOKEN_KEY)
}

/** 读取本地用户信息 */
export function getUserInfo(): UserInfo | null {
  return readJson<UserInfo>(USER_KEY)
}

/** 写入本地用户信息 */
export function setUserInfo(userInfo: UserInfo) {
  localStorage.setItem(USER_KEY, JSON.stringify(userInfo))
}

/** 清除本地用户信息 */
export function removeUserInfo() {
  localStorage.removeItem(USER_KEY)
}

/** 读取本地菜单缓存 */
export function getCachedMenus(): MenuNode[] {
  return readJson<MenuNode[]>(MENUS_KEY) ?? []
}

/** 登出：清空 token / 用户 / 菜单 / 权限，并触发内存态清理钩子 */
export function logout() {
  removeToken()
  removeUserInfo()
  localStorage.removeItem(MENUS_KEY)
  localStorage.removeItem(PERMS_KEY)
  logoutHandler?.()
}
