import { request } from '@/utils/request'
import type { UserInfo } from '@/types'

export interface UpdateProfileParams {
  name?: string
  email?: string
  phone?: string
  avatar?: string
}

export interface UpdatePasswordParams {
  old_password: string
  new_password: string
}

/** 获取当前登录用户信息 */
export function getMeApi() {
  return request<UserInfo>({
    url: '/api/user/me',
    method: 'get'
  })
}

/** 更新当前登录用户信息 */
export function updateMeApi(data: UpdateProfileParams) {
  return request<UserInfo>({
    url: '/api/user/me',
    method: 'put',
    data
  })
}

/** 修改当前登录用户密码 */
export function updatePasswordApi(data: UpdatePasswordParams) {
  return request<null>({
    url: '/api/user/password',
    method: 'put',
    data
  })
}
