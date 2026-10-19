import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode
} from 'react'

import {
  MENUS_KEY,
  PERMS_KEY,
  getCachedMenus,
  getUserInfo,
  onLogout,
  readJson,
  setToken,
  setUserInfo,
  writeJson
} from '@/utils/auth'
import type { LoginResult, MenuNode, UserInfo } from '@/types'

interface UserContextValue {
  /** 当前登录用户 */
  userInfo: UserInfo | null
  /** 菜单树 */
  menus: MenuNode[]
  /** 权限码集合 */
  permissions: string[]
  /** 登录成功后写入 token、用户信息与权限 */
  saveLoginData: (data: LoginResult) => void
  /** 更新本地与内存中的用户信息（含权限） */
  updateUser: (user: UserInfo) => void
  /** 从 localStorage 重新加载用户信息到内存 */
  reloadUser: () => void
  /** 设置菜单树并持久化 */
  setMenus: (list: MenuNode[]) => void
  /** 清空菜单/权限内存态与本地缓存 */
  clearAuthExtra: () => void
  /** 加载菜单（优先用户信息中的菜单，其次本地缓存） */
  loadMenus: () => Promise<void>
  /** 是否拥有指定角色码 */
  hasRole: (code: string) => boolean
  /** 是否拥有任一指定角色码 */
  hasAnyRole: (codes: string[]) => boolean
  /** 是否拥有指定权限码 */
  hasPermission: (code: string) => boolean
  /** 当前菜单树中全部可访问 path */
  getMenuPaths: () => string[]
}

const UserContext = createContext<UserContextValue | null>(null)

/** 递归收集菜单树中所有 path */
function collectPaths(list: MenuNode[], out: string[] = []): string[] {
  for (const item of list) {
    if (item.path) out.push(item.path)
    if (item.children?.length) collectPaths(item.children, out)
  }
  return out
}

export function UserProvider({ children }: { children: ReactNode }) {
  const [userInfo, setUserInfoState] = useState<UserInfo | null>(() => getUserInfo())
  const [menus, setMenusState] = useState<MenuNode[]>(() => getCachedMenus())
  const [permissions, setPermissionsState] = useState<string[]>(
    () => readJson<string[]>(PERMS_KEY) ?? []
  )

  const setMenus = useCallback((list: MenuNode[]) => {
    const next = list ?? []
    setMenusState(next)
    writeJson(MENUS_KEY, next)
  }, [])

  const clearAuthExtra = useCallback(() => {
    setMenusState([])
    setPermissionsState([])
    localStorage.removeItem(MENUS_KEY)
    localStorage.removeItem(PERMS_KEY)
  }, [])

  // 登出时同步清空内存态（auth 不反向 import 本文件，避免循环依赖）
  useEffect(() => {
    onLogout(clearAuthExtra)
  }, [clearAuthExtra])

  const applyPermissions = useCallback((perms?: string[]) => {
    if (!perms) return
    setPermissionsState(perms)
    writeJson(PERMS_KEY, perms)
  }, [])

  const saveLoginData = useCallback(
    (data: LoginResult) => {
      setToken(data.token)
      setUserInfo(data.user)
      setUserInfoState(data.user)
      applyPermissions(data.user?.permissions)
      if (data.user?.menus?.length) {
        setMenus(data.user.menus)
      }
    },
    [applyPermissions, setMenus]
  )

  const updateUser = useCallback(
    (user: UserInfo) => {
      setUserInfo(user)
      setUserInfoState(user)
      applyPermissions(user?.permissions)
    },
    [applyPermissions]
  )

  const reloadUser = useCallback(() => {
    setUserInfoState(getUserInfo())
  }, [])

  const loadMenus = useCallback(async () => {
    // 后端暂未提供独立菜单接口：优先使用登录响应/本地缓存中的菜单树。
    const cached = getCachedMenus()
    if (cached.length) {
      setMenusState(cached)
      return
    }
    const fromUser = userInfo?.menus ?? []
    if (fromUser.length) {
      setMenus(fromUser)
    }
  }, [userInfo, setMenus])

  const hasRole = useCallback(
    (code: string) => {
      const roles = userInfo?.roles ?? []
      if (roles.length) return roles.some((role) => role.code === code)
      return userInfo?.role === code
    },
    [userInfo]
  )

  const hasAnyRole = useCallback(
    (codes: string[]) => codes.some((code) => hasRole(code)),
    [hasRole]
  )

  const hasPermission = useCallback(
    (code: string) => permissions.includes(code),
    [permissions]
  )

  const getMenuPaths = useCallback(() => collectPaths(menus), [menus])

  const value = useMemo<UserContextValue>(
    () => ({
      userInfo,
      menus,
      permissions,
      saveLoginData,
      updateUser,
      reloadUser,
      setMenus,
      clearAuthExtra,
      loadMenus,
      hasRole,
      hasAnyRole,
      hasPermission,
      getMenuPaths
    }),
    [
      userInfo,
      menus,
      permissions,
      saveLoginData,
      updateUser,
      reloadUser,
      setMenus,
      clearAuthExtra,
      loadMenus,
      hasRole,
      hasAnyRole,
      hasPermission,
      getMenuPaths
    ]
  )

  return <UserContext.Provider value={value}>{children}</UserContext.Provider>
}

/** 读取用户/菜单/权限状态与鉴权辅助方法 */
export function useUser() {
  const ctx = useContext(UserContext)
  if (!ctx) {
    throw new Error('useUser 必须在 <UserProvider> 内使用')
  }
  return ctx
}
