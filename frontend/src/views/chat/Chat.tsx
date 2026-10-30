import {
  Children,
  cloneElement,
  isValidElement,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactElement,
  type ReactNode
} from 'react'
import {
  Avatar,
  Button,
  Empty,
  Input,
  Popover,
  Space,
  Spin,
  Typography
} from 'antd'
import {
  PlusOutlined,
  RobotOutlined,
  SendOutlined,
  StopOutlined,
  UserOutlined
} from '@ant-design/icons'
import dayjs from 'dayjs'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

import {
  confirmActionApi,
  getMessagesApi,
  getSessionsApi,
  streamChatApi
} from '@/api/chat'
import { feedback } from '@/utils/feedback'
import type {
  ChatCitation,
  ChatMessage,
  ChatPendingAction,
  ChatSession
} from '@/types'

const QUICK_PROMPTS = [
  '今天还有哪些空会议室？',
  '我有哪些预约？',
  '年假怎么申请？',
  '帮我订明天 10 点的会议室'
]

/** 行内引用上标：悬浮或点击展示知识库原文 */
function CitationBadge({ citation }: { citation: ChatCitation }) {
  return (
    <Popover
      trigger={['hover', 'click']}
      placement="top"
      content={
        <div className="citation-popover">
          <div className="citation-popover-title">
            {citation.document_name}
            {citation.page_no ? ` · 第 ${citation.page_no} 页` : ''}
          </div>
          <div className="citation-popover-content">{citation.content}</div>
        </div>
      }
    >
      <sup className="citation-ref">[{citation.index ?? 0}]</sup>
    </Popover>
  )
}

/** 把纯文本中的 [n] 替换成引用上标 */
function splitCitationText(
  text: string,
  citations: ChatCitation[],
  keyPrefix: string
): ReactNode {
  return text.split(/(\[\d+\])/g).map((part, index) => {
    const match = /^\[(\d+)\]$/.exec(part)
    if (!match) return part
    const citationIndex = Number(match[1])
    const citation =
      citations.find((item) => item.index === citationIndex) ??
      citations[citationIndex - 1]
    if (!citation) return part
    return (
      <CitationBadge
        key={`${keyPrefix}-${index}`}
        citation={{ ...citation, index: citation.index ?? citationIndex }}
      />
    )
  })
}

/** 递归处理 Markdown 子节点，保留原有结构 */
function renderCitations(
  children: ReactNode,
  citations: ChatCitation[]
): ReactNode {
  return Children.map(children, (child, index) => {
    if (typeof child === 'string') {
      return splitCitationText(child, citations, `text-${index}`)
    }
    if (isValidElement(child)) {
      const element = child as ReactElement<{ children?: ReactNode }>
      if (element.props.children) {
        return cloneElement(element, {
          children: renderCitations(element.props.children, citations)
        })
      }
    }
    return child
  })
}

function MarkdownContent({
  content,
  citations
}: {
  content: string
  citations?: ChatCitation[]
}) {
  const components = useMemo<Components>(() => {
    const items = citations ?? []
    return {
      p: ({ children }) => <p>{renderCitations(children, items)}</p>,
      li: ({ children }) => <li>{renderCitations(children, items)}</li>,
      td: ({ children }) => <td>{renderCitations(children, items)}</td>,
      th: ({ children }) => <th>{renderCitations(children, items)}</th>,
      strong: ({ children }) => (
        <strong>{renderCitations(children, items)}</strong>
      ),
      em: ({ children }) => <em>{renderCitations(children, items)}</em>,
      h1: ({ children }) => <h1>{renderCitations(children, items)}</h1>,
      h2: ({ children }) => <h2>{renderCitations(children, items)}</h2>,
      h3: ({ children }) => <h3>{renderCitations(children, items)}</h3>,
      h4: ({ children }) => <h4>{renderCitations(children, items)}</h4>
    }
  }, [citations])

  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {content}
    </ReactMarkdown>
  )
}

export default function Chat() {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [confirmingToken, setConfirmingToken] = useState<string | null>(null)

  const abortRef = useRef<AbortController | null>(null)
  const bottomRef = useRef<HTMLDivElement | null>(null)
  const skipLoadRef = useRef(false)

  const loadSessions = useCallback(async () => {
    try {
      const res = await getSessionsApi()
      setSessions(res.data)
    } catch {
      // 错误提示由请求拦截器统一处理
    }
  }, [])

  useEffect(() => {
    void loadSessions()
  }, [loadSessions])

  useEffect(() => {
    if (sessionId === null) {
      setMessages([])
      return
    }
    if (skipLoadRef.current) {
      skipLoadRef.current = false
      return
    }

    let cancelled = false
    setLoadingMessages(true)
    getMessagesApi(sessionId)
      .then((res) => {
        if (cancelled) return
        setMessages(
          res.data.map((message) => ({
            ...message,
            citations: message.citations?.map((citation, index) => ({
              ...citation,
              index: citation.index ?? index + 1
            }))
          }))
        )
      })
      .catch(() => {
        // 错误提示由请求拦截器统一处理
      })
      .finally(() => {
        if (!cancelled) setLoadingMessages(false)
      })
    return () => {
      cancelled = true
    }
  }, [sessionId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = useCallback(
    async (raw?: string) => {
      const text = (raw ?? input).trim()
      if (!text || streaming) return

      const assistantId = `a-${Date.now()}`
      setMessages((prev) => [
        ...prev,
        { id: `u-${Date.now()}`, role: 'user', content: text },
        { id: assistantId, role: 'assistant', content: '', citations: [] }
      ])
      setInput('')
      setStreaming(true)

      const controller = new AbortController()
      abortRef.current = controller
      let createdSessionId: number | null = sessionId

      try {
        await streamChatApi(
          { session_id: sessionId, message: text },
          {
            onMeta: (data) => {
              createdSessionId = data.session_id
            },
            onDelta: (data) => {
              setMessages((prev) =>
                prev.map((item) =>
                  item.id === assistantId
                    ? { ...item, content: item.content + data.content }
                    : item
                )
              )
            },
            onCitation: (data) => {
              setMessages((prev) =>
                prev.map((item) =>
                  item.id === assistantId
                    ? { ...item, citations: [...(item.citations ?? []), data] }
                    : item
                )
              )
            },
            onAction: (data) => {
              setMessages((prev) =>
                prev.map((item) =>
                  item.id === assistantId
                    ? { ...item, pendingAction: data }
                    : item
                )
              )
            },
            onDone: (data) => {
              if (data.answer) {
                setMessages((prev) =>
                  prev.map((item) =>
                    item.id === assistantId
                      ? { ...item, content: data.answer as string }
                      : item
                  )
                )
              }
            },
            onError: (message) => {
              setMessages((prev) =>
                prev.map((item) =>
                  item.id === assistantId
                    ? { ...item, content: item.content || message }
                    : item
                )
              )
            }
          },
          controller.signal
        )
      } catch (error) {
        if (!controller.signal.aborted) {
          const message =
            error instanceof Error ? error.message : '对话请求失败'
          setMessages((prev) =>
            prev.map((item) =>
              item.id === assistantId
                ? { ...item, content: item.content || message }
                : item
            )
          )
          feedback.error(message)
        }
      } finally {
        setStreaming(false)
        abortRef.current = null
        if (createdSessionId !== null && createdSessionId !== sessionId) {
          skipLoadRef.current = true
          setSessionId(createdSessionId)
        }
        await loadSessions()
      }
    },
    [input, loadSessions, sessionId, streaming]
  )

  async function handleConfirm(
    messageId: ChatMessage['id'],
    action: ChatPendingAction,
    approve: boolean
  ) {
    setConfirmingToken(action.token)
    try {
      const res = await confirmActionApi(action.token, approve)
      setMessages((prev) => [
        ...prev.map((item) =>
          item.id === messageId ? { ...item, pendingAction: undefined } : item
        ),
        {
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: res.data.message
        }
      ])
      feedback.success(approve ? '操作已完成' : '已取消操作')
      void loadSessions()
    } catch {
      // 错误提示由请求拦截器统一处理
    } finally {
      setConfirmingToken(null)
    }
  }

  function newChat() {
    if (streaming) return
    setSessionId(null)
    setMessages([])
    setInput('')
  }

  return (
    <div className="chat-page">
      <aside className="chat-sessions">
        <div className="chat-sessions-head">
          <span>对话</span>
          <Button
            size="small"
            type="primary"
            icon={<PlusOutlined />}
            onClick={newChat}
          >
            新对话
          </Button>
        </div>
        <div className="chat-session-list">
          {sessions.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无历史会话"
            />
          ) : (
            sessions.map((session) => (
              <button
                type="button"
                key={session.id}
                className={`chat-session-item ${
                  session.id === sessionId ? 'active' : ''
                }`}
                onClick={() => {
                  if (!streaming) setSessionId(session.id)
                }}
              >
                <span className="chat-session-title">{session.title}</span>
                <span className="chat-session-time">
                  {dayjs(session.update_time).format('MM-DD HH:mm')}
                </span>
              </button>
            ))
          )}
        </div>
      </aside>

      <section className="chat-main">
        <div className="chat-messages">
          {loadingMessages ? (
            <div className="chat-loading">
              <Spin />
            </div>
          ) : messages.length === 0 ? (
            <div className="chat-welcome">
              <RobotOutlined className="chat-welcome-icon" />
              <Typography.Title level={4} style={{ margin: 0 }}>
                你好，我是公司智能助手
              </Typography.Title>
              <Typography.Text type="secondary">
                可以问我会议室空闲情况、预约记录、员工手册和 IT 指南等问题。
              </Typography.Text>
              <div className="chat-quick">
                {QUICK_PROMPTS.map((prompt) => (
                  <Button key={prompt} onClick={() => void send(prompt)}>
                    {prompt}
                  </Button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message) => (
              <div
                key={message.id}
                className={`chat-message ${message.role}`}
              >
                <Avatar
                  className="chat-avatar"
                  icon={
                    message.role === 'user' ? (
                      <UserOutlined />
                    ) : (
                      <RobotOutlined />
                    )
                  }
                />
                <div className="chat-bubble">
                  <div
                    className={`chat-content ${
                      message.role === 'assistant' ? 'chat-markdown' : ''
                    }`}
                  >
                    {message.role === 'assistant' ? (
                      <MarkdownContent
                        content={
                          message.content ||
                          (streaming ? '正在思考…' : '')
                        }
                        citations={message.citations}
                      />
                    ) : (
                      message.content
                    )}
                  </div>

                  {message.pendingAction ? (
                    <div className="chat-action-card">
                      <div className="chat-action-title">待确认操作</div>
                      <div className="chat-action-summary">
                        {message.pendingAction.summary}
                      </div>
                      <Space>
                        <Button
                          type="primary"
                          size="small"
                          loading={
                            confirmingToken === message.pendingAction.token
                          }
                          onClick={() =>
                            void handleConfirm(
                              message.id,
                              message.pendingAction!,
                              true
                            )
                          }
                        >
                          确认
                        </Button>
                        <Button
                          size="small"
                          loading={
                            confirmingToken === message.pendingAction.token
                          }
                          onClick={() =>
                            void handleConfirm(
                              message.id,
                              message.pendingAction!,
                              false
                            )
                          }
                        >
                          取消
                        </Button>
                      </Space>
                    </div>
                  ) : null}
                </div>
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>

        <div className="chat-input-area">
          <Input.TextArea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            autoSize={{ minRows: 1, maxRows: 4 }}
            placeholder="输入问题，Enter 发送，Shift+Enter 换行"
            onPressEnter={(event) => {
              if (event.nativeEvent.isComposing) return
              if (!event.shiftKey) {
                event.preventDefault()
                void send()
              }
            }}
            disabled={streaming}
          />
          {streaming ? (
            <Button
              danger
              icon={<StopOutlined />}
              onClick={() => abortRef.current?.abort()}
            >
              停止
            </Button>
          ) : (
            <Button
              type="primary"
              icon={<SendOutlined />}
              disabled={!input.trim()}
              onClick={() => void send()}
            >
              发送
            </Button>
          )}
        </div>
      </section>
    </div>
  )
}
