import { useCallback, useEffect, useState } from 'react'
import {
  App as AntdApp,
  Button,
  Card,
  Empty,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  type TableProps
} from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'

import { getRoomsApi } from '@/api/room'
import {
  cancelReservationApi,
  getMyReservationsApi,
  type ReservationScope
} from '@/api/reservation'
import BookingModal from '@/components/BookingModal'
import { feedback } from '@/utils/feedback'
import type { MeetingRoom, Reservation } from '@/types'

const PAGE_SIZE = 10

/** 预约状态标签：取消/已结束为历史态，进行中与即将开始为有效态 */
function renderStatus(reservation: Reservation) {
  if (reservation.status === 'cancelled') {
    return <Tag>已取消</Tag>
  }
  const now = dayjs()
  if (dayjs(reservation.end_time).isBefore(now)) {
    return <Tag>已结束</Tag>
  }
  if (dayjs(reservation.start_time).isBefore(now)) {
    return <Tag color="processing">进行中</Tag>
  }
  return <Tag color="blue">即将开始</Tag>
}

export default function MyBookings() {
  const { modal } = AntdApp.useApp()
  const [scope, setScope] = useState<ReservationScope>('upcoming')
  const [page, setPage] = useState(1)
  const [list, setList] = useState<Reservation[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [rooms, setRooms] = useState<MeetingRoom[]>([])
  const [editing, setEditing] = useState<Reservation | null>(null)
  const [modalOpen, setModalOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getMyReservationsApi({
        scope,
        page,
        page_size: PAGE_SIZE
      })
      setList(res.data.list)
      setTotal(res.data.total)
    } catch {
      // 错误提示由请求拦截器统一处理
    } finally {
      setLoading(false)
    }
  }, [page, scope])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    getRoomsApi()
      .then((res) => setRooms(res.data))
      .catch(() => {
        // 会议室列表加载失败不影响预约列表
      })
  }, [])

  function confirmCancel(reservation: Reservation) {
    modal.confirm({
      title: '取消预约',
      content: `确定取消「${reservation.title}」（${dayjs(
        reservation.start_time
      ).format('MM-DD HH:mm')}）吗？`,
      okText: '确定取消',
      okButtonProps: { danger: true },
      cancelText: '再想想',
      onOk: async () => {
        try {
          await cancelReservationApi(reservation.id)
          feedback.success('已取消预约')
          if (list.length === 1 && page > 1) {
            setPage(page - 1)
          } else {
            await load()
          }
        } catch {
          // 错误提示由请求拦截器统一处理
        }
      }
    })
  }

  const columns: TableProps<Reservation>['columns'] = [
    {
      title: '会议室',
      dataIndex: 'room_name',
      width: 160
    },
    {
      title: '会议主题',
      dataIndex: 'title',
      ellipsis: true
    },
    {
      title: '时间',
      width: 220,
      render: (_, record) =>
        `${dayjs(record.start_time).format('MM-DD HH:mm')} - ${dayjs(
          record.end_time
        ).format('HH:mm')}`
    },
    {
      title: '状态',
      width: 110,
      render: (_, record) => renderStatus(record)
    },
    {
      title: '操作',
      width: 150,
      render: (_, record) => {
        const editable =
          record.status === 'confirmed' &&
          dayjs(record.start_time).isAfter(dayjs())
        if (!editable) {
          return <Typography.Text type="secondary">—</Typography.Text>
        }
        return (
          <Space size={0}>
            <Button
              type="link"
              size="small"
              onClick={() => {
                setEditing(record)
                setModalOpen(true)
              }}
            >
              修改
            </Button>
            <Button
              type="link"
              size="small"
              danger
              onClick={() => confirmCancel(record)}
            >
              取消
            </Button>
          </Space>
        )
      }
    }
  ]

  return (
    <div className="page-stack">
      <Card
        variant="borderless"
        title="我的预约"
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>
            刷新
          </Button>
        }
      >
        <Tabs
          activeKey={scope}
          onChange={(key) => {
            setScope(key as ReservationScope)
            setPage(1)
          }}
          items={[
            { key: 'upcoming', label: '即将开始' },
            { key: 'history', label: '历史记录' }
          ]}
        />

        <Table<Reservation>
          rowKey="id"
          columns={columns}
          dataSource={list}
          loading={loading}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  scope === 'upcoming' ? '暂无即将开始的预约' : '暂无历史预约'
                }
              />
            )
          }}
          pagination={{
            current: page,
            pageSize: PAGE_SIZE,
            total,
            showSizeChanger: false,
            onChange: (nextPage) => setPage(nextPage)
          }}
        />
      </Card>

      <BookingModal
        open={modalOpen}
        rooms={rooms}
        initial={editing ?? undefined}
        onClose={() => {
          setModalOpen(false)
          setEditing(null)
        }}
        onSuccess={() => {
          setModalOpen(false)
          setEditing(null)
          void load()
        }}
      />
    </div>
  )
}
