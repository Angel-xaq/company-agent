import { useCallback, useEffect, useState } from 'react'
import {
  App as AntdApp,
  Button,
  Card,
  Empty,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload,
  type TableProps
} from 'antd'
import { InboxOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'

import {
  deleteDocumentApi,
  getDocumentsApi,
  reindexDocumentApi,
  uploadDocumentApi
} from '@/api/knowledge'
import { useUser } from '@/store/UserContext'
import { feedback } from '@/utils/feedback'
import type { KnowledgeDocument } from '@/types'

const PAGE_SIZE = 10

const CATEGORY_LABELS: Record<string, string> = {
  handbook: '员工手册',
  it: 'IT 指南',
  policy: '规章制度',
  general: '通用'
}

const STATUS_LABELS: Record<string, { text: string; color: string }> = {
  pending: { text: '待索引', color: 'default' },
  processing: { text: '索引中', color: 'processing' },
  ready: { text: '已就绪', color: 'success' },
  failed: { text: '失败', color: 'error' }
}

function formatSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

export default function Knowledge() {
  const { modal } = AntdApp.useApp()
  const { hasPermission } = useUser()
  const canManage = hasPermission('kb:manage')

  const [list, setList] = useState<KnowledgeDocument[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [category, setCategory] = useState<string | undefined>()
  const [loading, setLoading] = useState(false)

  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [docName, setDocName] = useState('')
  const [docCategory, setDocCategory] = useState('general')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getDocumentsApi({
        keyword: keyword || undefined,
        category,
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
  }, [category, keyword, page])

  useEffect(() => {
    void load()
  }, [load])

  function openUpload() {
    setFile(null)
    setDocName('')
    setDocCategory('general')
    setUploadOpen(true)
  }

  async function handleUpload() {
    if (!file) {
      feedback.error('请选择要上传的文件')
      return
    }
    setUploading(true)
    try {
      await uploadDocumentApi(file, docName || undefined, docCategory)
      feedback.success('上传成功，后台索引中；完成后点击刷新查看状态')
      setUploadOpen(false)
      setPage(1)
      await load()
    } catch {
      // 错误提示由请求拦截器统一处理
    } finally {
      setUploading(false)
    }
  }

  function handleDelete(record: KnowledgeDocument) {
    modal.confirm({
      title: '删除文档',
      content: `确定删除「${record.name}」吗？删除后向量与切片将一并清理。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteDocumentApi(record.id)
          feedback.success('删除成功')
          await load()
        } catch {
          // 错误提示由请求拦截器统一处理
        }
      }
    })
  }

  async function handleReindex(record: KnowledgeDocument) {
    try {
      await reindexDocumentApi(record.id)
      feedback.success('已提交重建索引；完成后点击刷新查看状态')
      await load()
    } catch {
      // 错误提示由请求拦截器统一处理
    }
  }

  const columns: TableProps<KnowledgeDocument>['columns'] = [
    {
      title: '文档',
      dataIndex: 'name',
      render: (_, record) => (
        <div>
          <div style={{ fontWeight: 500 }}>{record.name}</div>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {record.filename} · {formatSize(record.file_size)}
          </Typography.Text>
        </div>
      )
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 110,
      render: (value: string) => (
        <Tag>{CATEGORY_LABELS[value] || value}</Tag>
      )
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 120,
      render: (_, record) => {
        const meta = STATUS_LABELS[record.status] || {
          text: record.status,
          color: 'default'
        }
        const tag = <Tag color={meta.color}>{meta.text}</Tag>
        if (record.status === 'failed' && record.error_message) {
          return <Tooltip title={record.error_message}>{tag}</Tooltip>
        }
        return tag
      }
    },
    {
      title: '切片',
      dataIndex: 'chunk_count',
      width: 80,
      render: (value: number) => value || '-'
    },
    {
      title: '上传人',
      dataIndex: 'uploader_name',
      width: 110
    },
    {
      title: '更新时间',
      dataIndex: 'update_time',
      width: 160,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm')
    }
  ]

  if (canManage) {
    columns.push({
      title: '操作',
      width: 170,
      render: (_, record) => (
        <Space size={0}>
          <Button type="link" size="small" onClick={() => void handleReindex(record)}>
            重建索引
          </Button>
          <Button type="link" size="small" danger onClick={() => handleDelete(record)}>
            删除
          </Button>
        </Space>
      )
    })
  }

  return (
    <div className="page-stack">
      <Card
        variant="borderless"
        title="知识库"
        extra={
          <Space wrap>
            <Input.Search
              allowClear
              placeholder="搜索文档名称"
              style={{ width: 220 }}
              onSearch={(value) => {
                setKeyword(value.trim())
                setPage(1)
              }}
            />
            <Select
              allowClear
              placeholder="全部分类"
              style={{ width: 130 }}
              value={category}
              onChange={(value) => {
                setCategory(value)
                setPage(1)
              }}
              options={Object.entries(CATEGORY_LABELS).map(([value, label]) => ({
                value,
                label
              }))}
            />
            <Button icon={<ReloadOutlined />} onClick={() => void load()}>
              刷新
            </Button>
            {canManage && (
              <Button type="primary" icon={<UploadOutlined />} onClick={openUpload}>
                上传文档
              </Button>
            )}
          </Space>
        }
      >
        <Table<KnowledgeDocument>
          rowKey="id"
          columns={columns}
          dataSource={list}
          loading={loading}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="暂无知识库文档"
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

      <Modal
        open={uploadOpen}
        title="上传知识库文档"
        okText="上传并索引"
        cancelText="取消"
        confirmLoading={uploading}
        onOk={() => void handleUpload()}
        onCancel={() => setUploadOpen(false)}
        destroyOnHidden
      >
        <Upload.Dragger
          accept=".pdf,.docx,.md,.txt"
          maxCount={1}
          beforeUpload={(selected) => {
            setFile(selected)
            if (!docName) {
              setDocName(selected.name.replace(/\.[^.]+$/, ''))
            }
            return false
          }}
          onRemove={() => setFile(null)}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽文件到此处</p>
          <p className="ant-upload-hint">
            支持 PDF、DOCX、Markdown、TXT，单文件不超过 20MB
          </p>
        </Upload.Dragger>

        <div style={{ marginTop: 16 }}>
          <Typography.Text>显示名称</Typography.Text>
          <Input
            value={docName}
            onChange={(event) => setDocName(event.target.value)}
            placeholder="例如：员工手册"
            maxLength={200}
            style={{ marginTop: 6 }}
          />
        </div>

        <div style={{ marginTop: 12 }}>
          <Typography.Text>分类</Typography.Text>
          <Select
            value={docCategory}
            onChange={setDocCategory}
            style={{ width: '100%', marginTop: 6 }}
            options={Object.entries(CATEGORY_LABELS).map(([value, label]) => ({
              value,
              label
            }))}
          />
        </div>
      </Modal>
    </div>
  )
}
