import axios, {
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig
} from 'axios'

import {
  PERMS_KEY,
  getToken,
  logout,
  setToken,
  setUserInfo,
  writeJson
} from '@/utils/auth'
import { feedback } from '@/utils/feedback'
import type { ApiResponse, LoginResult } from '@/types'

declare module 'axios' {
  export interface AxiosRequestConfig {
    /** 标记该请求已经重试过，避免刷新死循环 */
    _retry?: boolean
  }
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const service = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
  withCredentials: true
})

let refreshPromise: Promise<string | null> | null = null

/** 登录失效时整页跳回登录页，避免依赖路由实例 */
function redirectToLogin() {
  if (window.location.pathname !== '/login') {
    window.location.replace('/login')
  }
}

/** 登录、刷新、退出接口不参与自动续期 */
function isAuthEndpoint(url?: string) {
  if (!url) return false
  return (
    url.includes('/api/auth/login') ||
    url.includes('/api/auth/register') ||
    url.includes('/api/auth/refresh') ||
    url.includes('/api/auth/logout')
  )
}

/** 使用 HttpOnly Cookie 中的 Refresh Token 换取新的 Access Token */
async function refreshAccessToken(): Promise<string | null> {
  try {
    const response = await axios.post<ApiResponse<LoginResult>>(
      `${API_BASE_URL}/api/auth/refresh`,
      {},
      { withCredentials: true, timeout: 15000 }
    )
    const data = response.data
    if (data.code !== 200 || !data.data?.token) {
      return null
    }
    setToken(data.data.token)
    setUserInfo(data.data.user)
    writeJson(PERMS_KEY, data.data.user.permissions ?? [])
    return data.data.token
  } catch {
    return null
  }
}

// 请求拦截器：统一携带 Access Token
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

// 响应拦截器：统一处理业务码、401 自动续期与 HTTP 错误
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
  async (err) => {
    const original = err.config as InternalAxiosRequestConfig | undefined
    const status = err.response?.status as number | undefined

    if (
      status === 401 &&
      original &&
      !original._retry &&
      !isAuthEndpoint(original.url)
    ) {
      original._retry = true
      if (!refreshPromise) {
        refreshPromise = refreshAccessToken().finally(() => {
          refreshPromise = null
        })
      }
      const token = await refreshPromise
      if (token) {
        original.headers = original.headers ?? {}
        original.headers.Authorization = `Bearer ${token}`
        return service(original)
      }
      feedback.error('登录状态已失效，请重新登录')
      logout()
      redirectToLogin()
      return Promise.reject(err)
    }

    if (err.response) {
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
