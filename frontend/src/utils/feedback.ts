import { message as staticMessage } from 'antd'

/** antd 全局提示的轻量封装：优先使用 <App> 上下文实例，避免静态方法丢失主题 */
interface MessageApi {
  success: (content: string) => void
  error: (content: string) => void
  warning: (content: string) => void
}

let messageApi: MessageApi | null = null

/** 由 MessageBridge 在 <App> 上下文内注入 */
export function bindMessageApi(api: MessageApi) {
  messageApi = api
}

function getMessage(): MessageApi {
  return messageApi ?? staticMessage
}

export const feedback = {
  success: (content: string) => getMessage().success(content),
  error: (content: string) => getMessage().error(content),
  warning: (content: string) => getMessage().warning(content)
}
