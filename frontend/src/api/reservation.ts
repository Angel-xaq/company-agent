import { request } from '@/utils/request'
import type { PageResult, Reservation } from '@/types'

export type ReservationScope = 'upcoming' | 'history'

export interface ReservationQuery {
  scope: ReservationScope
  page: number
  page_size: number
}

export interface ReservationUpdatePayload {
  title?: string
  purpose?: string
  attendees?: number
  room_id?: number
  start_time?: string
  end_time?: string
}

/** 我的预约列表 */
export function getMyReservationsApi(params: ReservationQuery) {
  return request<PageResult<Reservation>>({
    url: '/api/reservations/mine',
    method: 'get',
    params
  })
}

/** 修改预约 */
export function updateReservationApi(id: number, data: ReservationUpdatePayload) {
  return request<Reservation>({
    url: `/api/reservations/${id}`,
    method: 'put',
    data
  })
}

/** 取消预约 */
export function cancelReservationApi(id: number, reason?: string) {
  return request<Reservation>({
    url: `/api/reservations/${id}/cancel`,
    method: 'post',
    data: reason ? { reason } : undefined
  })
}
