/** 角色精简信息 */
export interface RoleBrief {
  id: number
  code: string
  name: string
}

/** 后端返回的菜单节点 */
export interface MenuNode {
  id: number
  parent_id?: number | null
  name: string
  type?: 'dir' | 'menu' | 'button' | string
  path?: string | null
  component?: string | null
  icon?: string | null
  permission?: string | null
  sort?: number
  visible?: number
  status?: number
  children?: MenuNode[]
}

/** 当前登录用户 */
export interface UserInfo {
  id: number
  username: string
  name: string
  email?: string | null
  phone?: string | null
  avatar?: string | null
  status: number
  roles: RoleBrief[]
  permissions: string[]
  /** 兼容旧版单角色字段 */
  role?: string | null
  role_ids: number[]
  /** 若后端后续在登录响应中下发菜单树，可直接使用 */
  menus?: MenuNode[]
}

/** 统一响应结构 */
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

/** 分页响应 */
export interface PageResult<T> {
  list: T[]
  total: number
}

/** 登录响应 */
export interface LoginResult {
  token: string
  user: UserInfo
}
