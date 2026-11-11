import { getToken, logout } from '@/utils/auth'
import { request } from '@/utils/request'
import type {
  ChatCitation,
  ChatMessage,
  ChatPendingAction,
  ChatSession
} from '@/types'

export interface StreamMeta {
  session_id: number
}

export interface StreamDelta {
  content: string
}

export interface StreamDone {
  message_id: number
  session_id: number
  usage?: Record<string, number>
  /** 后端清洗后的完整正文（移除来源尾注） */
  answer?: string
}

export interface StreamHandlers {
  onMeta: (data: StreamMeta) => void
  onDelta: (data: StreamDelta) => void
  onCitation: (data: ChatCitation) => void
  onAction: (data: ChatPendingAction) => void
  onDone: (data: StreamDone) => void
  onError: (message: string) => void
}

/** 会话列表 */
export function getSessionsApi() {
  return request<ChatSession[]>({
    url: '/api/chat/sessions',
    method: 'get'
  })
}

/** 新建会话 */
export function createSessionApi() {
  return request<ChatSession>({
    url: '/api/chat/sessions',
    method: 'post'
  })
}

/** 会话历史消息 */
export function getMessagesApi(sessionId: number) {
  return request<ChatMessage[]>({
    url: `/api/chat/sessions/${sessionId}/messages`,
    method: 'get'
  })
}

/** 删除会话 */
export function deleteSessionApi(sessionId: number) {
  return request<null>({
    url: `/api/chat/sessions/${sessionId}`,
    method: 'delete'
  })
}

/** 当前会话待确认的写操作（刷新页面后回挂确认卡片） */
export function getPendingActionsApi(sessionId: number) {
  return request<ChatPendingAction[]>({
    url: '/api/chat/actions/pending',
    method: 'get',
    params: { session_id: sessionId }
  })
}

/** 读取后端 SSE 流（Axios 不支持流式读取，因此使用 fetch） */
async function readSse(
  path: string,
  payload: unknown,
  handlers: StreamHandlers,
  signal?: AbortSignal
) {
  const base = import.meta.env.VITE_API_BASE_URL || ''
  const token = getToken()
  const response = await fetch(`${base}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify(payload),
    signal
  })

  if (!response.ok || !response.body) {
    if (response.status === 401) {
      logout()
      window.location.replace('/login')
    }
    let message = '对话请求失败'
    try {
      const data = (await response.json()) as { message?: string }
      message = data.message || message
    } catch {
      // 忽略非 JSON 响应
    }
    throw new Error(message)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      let event = 'message'
      let data = ''
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) {
          event = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          data += line.slice(5).trim()
        }
      }
      if (!data) continue

      const parsed = JSON.parse(data) as Record<string, unknown>
      if (event === 'meta') handlers.onMeta(parsed as unknown as StreamMeta)
      else if (event === 'delta') handlers.onDelta(parsed as unknown as StreamDelta)
      else if (event === 'citation') {
        handlers.onCitation(parsed as unknown as ChatCitation)
      } else if (event === 'action') {
        handlers.onAction(parsed as unknown as ChatPendingAction)
      } else if (event === 'done') handlers.onDone(parsed as unknown as StreamDone)
      else if (event === 'error') {
        handlers.onError(String(parsed.message || '智能助手暂时不可用'))
      }
    }
  }
}

/** SSE 流式对话 */
export async function streamChatApi(
  payload: { session_id: number | null; message: string },
  handlers: StreamHandlers,
  signal?: AbortSignal
) {
  return readSse('/api/chat/stream', payload, handlers, signal)
}

/** 确认/拒绝待执行操作：同样是 SSE，事件类型与对话流一致 */
export async function confirmActionApi(
  token: string,
  approve: boolean,
  handlers: StreamHandlers,
  signal?: AbortSignal
) {
  return readSse(`/api/chat/actions/${token}`, { approve }, handlers, signal)
}
