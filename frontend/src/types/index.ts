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

/** 会议室 */
export interface MeetingRoom {
  id: number
  name: string
  location?: string | null
  capacity: number
  equipment: string[]
  description?: string | null
  status: number
  sort: number
}

/** 看板中的预约块 */
export interface BoardReservation {
  id: number
  title: string
  start_time: string
  end_time: string
  status: string
  mine: boolean
  user_name?: string | null
}

/** 看板中的会议室 */
export interface BoardRoom extends MeetingRoom {
  reservations: BoardReservation[]
}

/** 营业时间配置 */
export interface BusinessHours {
  start: string
  end: string
  slot_minutes: number
}

/** 看板响应 */
export interface BoardData {
  date: string
  server_time: string
  business_hours: BusinessHours
  rooms: BoardRoom[]
}

/** 预约记录 */
export interface Reservation {
  id: number
  room_id: number
  room_name: string
  user_id: number
  user_name: string
  title: string
  purpose?: string | null
  attendees?: number | null
  start_time: string
  end_time: string
  status: 'confirmed' | 'cancelled' | string
  cancelled_at?: string | null
  cancel_reason?: string | null
  create_time: string
  mine: boolean
}

/** 知识库文档 */
export interface KnowledgeDocument {
  id: number
  name: string
  category: string
  filename: string
  file_type: string
  file_size: number
  status: 'pending' | 'processing' | 'ready' | 'failed' | string
  chunk_count: number
  embedding_model?: string | null
  error_message?: string | null
  uploaded_by: number
  uploader_name: string
  create_time: string
  update_time: string
}

/** 知识库检索片段 */
export interface KnowledgeSearchItem {
  document_id: number
  document_name: string
  chunk_index: number
  content: string
  score: number
  page_no?: number | null
}

/** 对话会话 */
export interface ChatSession {
  id: number
  title: string
  create_time: string
  update_time: string
}

/** 知识库引用 */
export interface ChatCitation {
  /** 与答案中 [n] 对应的编号 */
  index?: number
  document_id: number
  document_name: string
  chunk_index: number
  content: string
  page_no?: number | null
  score?: number
}

/** 待确认操作 */
export interface ChatPendingAction {
  token: string
  tool_name: string
  params: Record<string, unknown>
  summary: string
}

/** 对话消息（前端展示用） */
export interface ChatMessage {
  id: number | string
  role: 'user' | 'assistant'
  content: string
  citations?: ChatCitation[]
  pendingAction?: ChatPendingAction
  create_time?: string
}
