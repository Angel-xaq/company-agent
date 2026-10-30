import { request } from '@/utils/request'
import type { BoardData, MeetingRoom, Reservation } from '@/types'

export interface ReservationPayload {
  title: string
  purpose?: string
  attendees?: number
  start_time: string
  end_time: string
}

/** 会议室看板 */
export function getBoardApi(date: string) {
  return request<BoardData>({
    url: '/api/rooms/board',
    method: 'get',
    params: { date }
  })
}

/** 会议室列表 */
export function getRoomsApi() {
  return request<MeetingRoom[]>({
    url: '/api/rooms',
    method: 'get'
  })
}

/** 创建预约 */
export function createReservationApi(roomId: number, data: ReservationPayload) {
  return request<Reservation>({
    url: `/api/rooms/${roomId}/reservations`,
    method: 'post',
    data
  })
}
