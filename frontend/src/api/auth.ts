import { request } from '@/utils/request'
import type { LoginResult } from '@/types'

export interface LoginParams {
  username: string
  password: string
}

export interface RegisterParams {
  username: string
  password: string
  name?: string
}

/** 账号密码登录 */
export function loginApi(data: LoginParams) {
  return request<LoginResult>({
    url: '/api/auth/login',
    method: 'post',
    data
  })
}

/** 注册新用户 */
export function registerApi(data: RegisterParams) {
  return request<null>({
    url: '/api/auth/register',
    method: 'post',
    data
  })
}
