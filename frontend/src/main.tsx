import { StrictMode, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { App as AntdApp, ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import 'antd/dist/reset.css'

import App from '@/App'
import { bindMessageApi } from '@/utils/feedback'
import '@/styles/global.css'

/** 将 <App> 上下文中的 message 实例交给请求层/工具函数使用 */
function MessageBridge() {
  const { message } = AntdApp.useApp()

  useEffect(() => {
    bindMessageApi(message)
  }, [message])

  return null
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{ token: { colorPrimary: '#1677ff', borderRadius: 8 } }}
    >
      <AntdApp>
        <MessageBridge />
        <App />
      </AntdApp>
    </ConfigProvider>
  </StrictMode>
)
