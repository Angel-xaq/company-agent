import { useEffect, useMemo, useState } from 'react'
import {
  Col,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select
} from 'antd'
import dayjs, { type Dayjs } from 'dayjs'

import { createReservationApi } from '@/api/room'
import { updateReservationApi } from '@/api/reservation'
import { feedback } from '@/utils/feedback'
import {
  buildEndSlots,
  buildStartSlots,
  fromMinutes,
  toMinutes
} from '@/utils/time'
import type { BusinessHours, MeetingRoom, Reservation } from '@/types'

interface BookingModalProps {
  open: boolean
  rooms: MeetingRoom[]
  businessHours?: BusinessHours
  preset?: { roomId: number; date: string; start: string }
  initial?: Reservation
  onClose: () => void
  onSuccess: () => void
}

interface BookingFormValues {
  room_id: number
  date: Dayjs
  start_time: string
  end_time: string
  title: string
  purpose?: string
  attendees?: number
}

const DEFAULT_BUSINESS: BusinessHours = {
  start: '09:30',
  end: '21:00',
  slot_minutes: 30
}

const MAX_MINUTES = 4 * 60

export default function BookingModal({
  open,
  rooms,
  businessHours = DEFAULT_BUSINESS,
  preset,
  initial,
  onClose,
  onSuccess
}: BookingModalProps) {
  const [form] = Form.useForm<BookingFormValues>()
  const [submitting, setSubmitting] = useState(false)
  const startTime = Form.useWatch('start_time', form)
  const roomId = Form.useWatch('room_id', form)

  const startSlots = useMemo(
    () =>
      buildStartSlots(
        businessHours.start,
        businessHours.end,
        businessHours.slot_minutes
      ),
    [businessHours]
  )

  const endSlots = useMemo(() => {
    if (!startTime) return []
    const start = toMinutes(startTime)
    const maxEnd = Math.min(start + MAX_MINUTES, toMinutes(businessHours.end))
    return buildEndSlots(
      businessHours.start,
      businessHours.end,
      businessHours.slot_minutes
    ).filter((slot) => {
      const value = toMinutes(slot)
      return value > start && value <= maxEnd
    })
  }, [businessHours, startTime])

  // 仅在打开时初始化，避免父组件刷新导致表单被重置
  useEffect(() => {
    if (!open) return
    form.resetFields()

    if (initial) {
      const start = dayjs(initial.start_time)
      const end = dayjs(initial.end_time)
      form.setFieldsValue({
        room_id: initial.room_id,
        date: start,
        start_time: start.format('HH:mm'),
        end_time: end.format('HH:mm'),
        title: initial.title,
        purpose: initial.purpose ?? '',
        attendees: initial.attendees ?? undefined
      })
      return
    }

    if (preset) {
      const start = toMinutes(preset.start)
      form.setFieldsValue({
        room_id: preset.roomId,
        date: dayjs(preset.date),
        start_time: preset.start,
        end_time: fromMinutes(
          Math.min(start + 60, toMinutes(businessHours.end))
        ),
        title: '',
        purpose: '',
        attendees: undefined
      })
      return
    }

    const start = toMinutes(businessHours.start)
    form.setFieldsValue({
      room_id: rooms[0]?.id,
      date: dayjs(),
      start_time: businessHours.start,
      end_time: fromMinutes(Math.min(start + 60, toMinutes(businessHours.end))),
      title: '',
      purpose: '',
      attendees: undefined
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // 开始时间变化后，保证结束时间仍然合法
  useEffect(() => {
    if (!startTime || endSlots.length === 0) return
    const current = form.getFieldValue('end_time') as string | undefined
    if (!current || !endSlots.includes(current)) {
      form.setFieldValue('end_time', endSlots[0])
    }
  }, [endSlots, form, startTime])

  const selectedRoom = rooms.find((room) => room.id === roomId)

  async function handleFinish(values: BookingFormValues) {
    const date = values.date.format('YYYY-MM-DD')
    const start = dayjs(`${date}T${values.start_time}:00`)
    const end = dayjs(`${date}T${values.end_time}:00`)

    if (!end.isAfter(start)) {
      feedback.error('结束时间必须晚于开始时间')
      return
    }
    if (end.diff(start, 'minute') > MAX_MINUTES) {
      feedback.error('单次预约不能超过 4 小时')
      return
    }

    const payload = {
      title: values.title.trim(),
      purpose: values.purpose?.trim() || undefined,
      attendees: values.attendees,
      start_time: start.format('YYYY-MM-DDTHH:mm:ssZ'),
      end_time: end.format('YYYY-MM-DDTHH:mm:ssZ')
    }

    setSubmitting(true)
    try {
      if (initial) {
        await updateReservationApi(initial.id, {
          ...payload,
          room_id: values.room_id
        })
        feedback.success('修改成功')
      } else {
        await createReservationApi(values.room_id, payload)
        feedback.success('预约成功')
      }
      form.resetFields()
      onSuccess()
      onClose()
    } catch {
      // 错误提示由请求拦截器统一处理
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      title={initial ? '修改预约' : '预约会议室'}
      okText={initial ? '保存修改' : '确认预约'}
      cancelText="取消"
      confirmLoading={submitting}
      onOk={() => form.submit()}
      onCancel={onClose}
      destroyOnHidden
      width={560}
    >
      <Form<BookingFormValues>
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={handleFinish}
      >
        <Form.Item
          label="会议室"
          name="room_id"
          rules={[{ required: true, message: '请选择会议室' }]}
          extra={
            selectedRoom
              ? `可容纳 ${selectedRoom.capacity} 人${
                  selectedRoom.equipment.length
                    ? ` · ${selectedRoom.equipment.join(' / ')}`
                    : ''
                }`
              : undefined
          }
        >
          <Select
            placeholder="请选择会议室"
            options={rooms.map((room) => ({
              value: room.id,
              label: `${room.name}（${room.capacity} 人）`
            }))}
          />
        </Form.Item>

        <Form.Item
          label="日期"
          name="date"
          rules={[{ required: true, message: '请选择日期' }]}
        >
          <DatePicker
            style={{ width: '100%' }}
            allowClear={false}
            disabledDate={(current) =>
              current.isBefore(dayjs().startOf('day')) ||
              current.isAfter(dayjs().add(30, 'day').endOf('day'))
            }
          />
        </Form.Item>

        <Row gutter={12}>
          <Col span={12}>
            <Form.Item
              label="开始时间"
              name="start_time"
              rules={[{ required: true, message: '请选择开始时间' }]}
            >
              <Select
                options={startSlots.map((slot) => ({ value: slot, label: slot }))}
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              label="结束时间"
              name="end_time"
              rules={[{ required: true, message: '请选择结束时间' }]}
            >
              <Select
                options={endSlots.map((slot) => ({ value: slot, label: slot }))}
              />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item
          label="会议主题"
          name="title"
          rules={[{ required: true, message: '请输入会议主题' }]}
        >
          <Input placeholder="例如：产品评审" maxLength={100} showCount />
        </Form.Item>

        <Form.Item label="用途说明" name="purpose">
          <Input placeholder="选填，例如：版本迭代评审" maxLength={255} />
        </Form.Item>

        <Form.Item label="参会人数" name="attendees">
          <InputNumber
            min={1}
            max={selectedRoom?.capacity}
            style={{ width: '100%' }}
            placeholder="选填"
          />
        </Form.Item>
      </Form>
    </Modal>
  )
}
