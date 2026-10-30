import { request } from '@/utils/request'
import type { UserInfo } from '@/types'

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

/** 修改当前登录用户密码 */
export function updatePasswordApi(data: UpdatePasswordParams) {
  return request<null>({
    url: '/api/user/password',
    method: 'put',
    data
  })
}
