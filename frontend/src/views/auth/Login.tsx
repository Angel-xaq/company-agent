import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Button, Card, Form, Input, Typography } from 'antd'
import { LockOutlined, UserOutlined } from '@ant-design/icons'

import { loginApi, type LoginParams } from '@/api/auth'
import { useUser } from '@/store/UserContext'
import { feedback } from '@/utils/feedback'

interface LocationState {
  from?: string
}

export default function Login() {
  const [loading, setLoading] = useState(false)
  const { saveLoginData } = useUser()
  const navigate = useNavigate()
  const location = useLocation()

  async function handleFinish(values: LoginParams) {
    setLoading(true)
    try {
      const res = await loginApi(values)
      saveLoginData(res.data)
      feedback.success('登录成功')
      const from = (location.state as LocationState | null)?.from
      navigate(from && from.startsWith('/manager') ? from : '/manager/home', {
        replace: true
      })
    } catch {
      // 错误提示已由 axios 拦截器统一处理
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-page">
      <Card variant="borderless" className="auth-card">
        <Typography.Title level={3} className="auth-title">
          公司智能管理系统
        </Typography.Title>
        <Typography.Paragraph type="secondary" className="auth-subtitle">
          基于 Agent 的智能管理系统
        </Typography.Paragraph>

        <Form<LoginParams> onFinish={handleFinish} size="large" requiredMark={false}>
          <Form.Item
            name="username"
            rules={[{ required: true, message: '请输入账号' }]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder="请输入账号"
              autoComplete="username"
            />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="请输入密码"
              autoComplete="current-password"
            />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" block loading={loading}>
              登 录
            </Button>
          </Form.Item>
        </Form>

        <div className="auth-footer" style={{ marginTop: 20 }}>
          还没有账号？请<Link to="/register">注册</Link>
        </div>
      </Card>
    </div>
  )
}
