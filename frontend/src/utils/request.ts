import axios, { type AxiosRequestConfig } from 'axios'

import { getToken, logout } from '@/utils/auth'
import { feedback } from '@/utils/feedback'
import type { ApiResponse } from '@/types'

const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 60000
})

/** 登录失效时整页跳回登录页，避免依赖路由实例 */
function redirectToLogin() {
  if (window.location.pathname !== '/login') {
    window.location.replace('/login')
  }
}

// 请求拦截器：统一携带 token
service.interceptors.request.use(
  (config) => {
    const token = getToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (err) => Promise.reject(err)
)

// 响应拦截器：统一处理业务码与 HTTP 错误
service.interceptors.response.use(
  (res) => {
    const data = res.data as ApiResponse
    if (data.code !== 200) {
      if (data.code === 401) {
        feedback.error(data.message || '登录已失效')
        logout()
        redirectToLogin()
      } else if (data.code === 403) {
        feedback.error(data.message || '无权限访问')
      } else {
        feedback.error(data.message || '请求失败')
      }
      return Promise.reject(data)
    }
    return data as never
  },
  (err) => {
    if (err.response) {
      const status = err.response.status as number
      const msg = err.response.data?.message as string | undefined
      if (status === 401) {
        feedback.error('登录状态已失效，请重新登录')
        logout()
        redirectToLogin()
      } else if (status === 403) {
        feedback.error(msg || '无权限访问')
      } else {
        feedback.error(msg || '请求失败')
      }
    } else {
      feedback.error('网络异常，请检查后端服务')
    }
    return Promise.reject(err)
  }
)

/** 发送请求，返回值已剥离 axios 包装，直接是统一响应结构 */
export async function request<T = unknown>(config: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return service.request(config) as Promise<ApiResponse<T>>
}

export default request
