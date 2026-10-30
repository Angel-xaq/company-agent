import { useMemo, useState } from 'react'
import {
  Button,
  Card,
  DatePicker,
  Empty,
  Space,
  Spin,
  Tag,
  Typography
} from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'

import BookingModal from '@/components/BookingModal'
import { useBoard } from '@/hooks/useBoard'
import { buildStartSlots } from '@/utils/time'
import type { BoardReservation, BoardRoom, BusinessHours } from '@/types'

const DEFAULT_BUSINESS: BusinessHours = {
  start: '09:30',
  end: '21:00',
  slot_minutes: 30
}

export default function RoomBoard() {
  const [date, setDate] = useState(() => dayjs().format('YYYY-MM-DD'))
  const [booking, setBooking] = useState<{ room: BoardRoom; start: string } | null>(
    null
  )
  const { data, loading, refresh } = useBoard(date)
  const board = data?.date === date ? data : null

  const businessHours = board?.business_hours ?? DEFAULT_BUSINESS
  const slots = useMemo(
    () =>
      buildStartSlots(
        businessHours.start,
        businessHours.end,
        businessHours.slot_minutes
      ),
    [businessHours]
  )

  const gridStyle = {
    gridTemplateColumns: `repeat(${slots.length}, minmax(54px, 1fr))`
  }

  /** 找到当前时段内覆盖的预约 */
  function findReservation(
    room: BoardRoom,
    slot: string
  ): BoardReservation | undefined {
    const slotStart = dayjs(`${date}T${slot}:00`)
    const slotEnd = slotStart.add(businessHours.slot_minutes, 'minute')
    return room.reservations.find((item) => {
      const start = dayjs(item.start_time)
      const end = dayjs(item.end_time)
      return start.isBefore(slotEnd) && end.isAfter(slotStart)
    })
  }

  const occupiedCount = useMemo(() => {
    if (!board) return 0
    const now = dayjs()
    return board.rooms.filter((room) =>
      room.reservations.some((item) => {
        const start = dayjs(item.start_time)
        const end = dayjs(item.end_time)
        return start.isBefore(now) && end.isAfter(now)
      })
    ).length
  }, [board])

  return (
    <div className="page-stack">
      <Card
        variant="borderless"
        title={
          <Space wrap>
            <span>会议室看板</span>
            <DatePicker
              value={dayjs(date)}
              allowClear={false}
              onChange={(value) => {
                if (value) setDate(value.format('YYYY-MM-DD'))
              }}
              disabledDate={(current) =>
                current.isBefore(dayjs().startOf('day')) ||
                current.isAfter(dayjs().add(30, 'day').endOf('day'))
              }
            />
          </Space>
        }
        extra={
          <Space>
            <Typography.Text type="secondary">
              共 {board?.rooms.length ?? 0} 间 · 当前占用 {occupiedCount} 间
            </Typography.Text>
            <Button icon={<ReloadOutlined />} onClick={() => void refresh()}>
              刷新
            </Button>
          </Space>
        }
      >
        {loading && !board ? (
          <div style={{ padding: 48, textAlign: 'center' }}>
            <Spin />
          </div>
        ) : !board?.rooms.length ? (
          <Empty description="暂无可用会议室" />
        ) : (
          <>
            <div className="room-board-scroll">
              <div className="room-board">
                <div className="room-board-row room-board-head">
                  <div className="room-board-meta">会议室</div>
                  <div className="room-board-slots" style={gridStyle}>
                    {slots.map((slot) => (
                      <div key={slot} className="room-slot-label">
                        {slot}
                      </div>
                    ))}
                  </div>
                </div>

                {board.rooms.map((room) => (
                  <div className="room-board-row" key={room.id}>
                    <div className="room-board-meta">
                      <strong>{room.name}</strong>
                      <span className="room-meta-sub">
                        {room.location || '未设置位置'} · {room.capacity} 人
                      </span>
                      <Space size={4} wrap>
                        {room.equipment.map((item) => (
                          <Tag key={item} color="blue">
                            {item}
                          </Tag>
                        ))}
                      </Space>
                    </div>
                    <div className="room-board-slots" style={gridStyle}>
                      {slots.map((slot) => {
                        const reservation = findReservation(room, slot)
                        if (!reservation) {
                          const slotStart = dayjs(`${date}T${slot}:00`)
                          if (slotStart.isBefore(dayjs())) {
                            return (
                              <div
                                key={slot}
                                className="room-slot disabled"
                                title="该时段已过去"
                              />
                            )
                          }
                          return (
                            <button
                              type="button"
                              key={slot}
                              className="room-slot free"
                              title={`预约 ${room.name} ${slot}`}
                              onClick={() => setBooking({ room, start: slot })}
                            />
                          )
                        }

                        const start = dayjs(reservation.start_time)
                        const end = dayjs(reservation.end_time)
                        const now = dayjs()
                        const isStart = start.format('HH:mm') === slot
                        const ongoing = start.isBefore(now) && end.isAfter(now)
                        return (
                          <div
                            key={slot}
                            className={[
                              'room-slot',
                              'occupied',
                              reservation.mine ? 'mine' : '',
                              ongoing ? 'ongoing' : ''
                            ]
                              .filter(Boolean)
                              .join(' ')}
                            title={`${reservation.title} · ${start.format(
                              'HH:mm'
                            )}-${end.format('HH:mm')}${
                              reservation.user_name
                                ? ` · ${reservation.user_name}`
                                : ''
                            }`}
                          >
                            {isStart ? reservation.title : ''}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="room-board-legend">
              <span>
                <i className="legend-block free" /> 空闲（点击预约）
              </span>
              <span>
                <i className="legend-block occupied" /> 已预约
              </span>
              <span>
                <i className="legend-block mine" /> 我的预约
              </span>
              <span>
                <i className="legend-block ongoing" /> 进行中
              </span>
              <Typography.Text type="secondary">
                营业时间 {businessHours.start}–{businessHours.end}，每{' '}
                {businessHours.slot_minutes} 分钟一个时段
              </Typography.Text>
            </div>
          </>
        )}
      </Card>

      <BookingModal
        open={Boolean(booking)}
        rooms={board?.rooms ?? []}
        businessHours={businessHours}
        preset={
          booking
            ? {
                roomId: booking.room.id,
                date,
                start: booking.start
              }
            : undefined
        }
        onClose={() => setBooking(null)}
        onSuccess={() => {
          setBooking(null)
          void refresh()
        }}
      />
    </div>
  )
}
