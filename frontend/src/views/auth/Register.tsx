import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button, Card, Form, Input, Typography } from 'antd'
import { LockOutlined, UserOutlined } from '@ant-design/icons'

import { registerApi } from '@/api/auth'
import { feedback } from '@/utils/feedback'

interface RegisterForm {
  username: string
  password: string
  confirmPassword: string
}

export default function Register() {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  async function handleFinish(values: RegisterForm) {
    setLoading(true)
    try {
      await registerApi({ username: values.username, password: values.password })
      feedback.success('注册成功')
      navigate('/login', { replace: true })
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
          欢迎注册
        </Typography.Title>
        <Typography.Paragraph type="secondary" className="auth-subtitle">
          注册后将默认绑定学生角色
        </Typography.Paragraph>

        <Form<RegisterForm> onFinish={handleFinish} size="large" requiredMark={false}>
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
            rules={[
              { required: true, message: '请输入密码' },
              { min: 6, max: 64, message: '密码长度为 6-64 位' }
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="请输入密码"
              autoComplete="new-password"
            />
          </Form.Item>
          <Form.Item
            name="confirmPassword"
            dependencies={['password']}
            rules={[
              { required: true, message: '请确认密码' },
              ({ getFieldValue }) => ({
                validator(_, value: string) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve()
                  }
                  return Promise.reject(new Error('两次密码输入不一致'))
                }
              })
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="请确认密码"
              autoComplete="new-password"
            />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" block loading={loading}>
              注 册
            </Button>
          </Form.Item>
        </Form>

        <div className="auth-footer" style={{ marginTop: 20 }}>
          已有账号？请<Link to="/login">登录</Link>
        </div>
      </Card>
    </div>
  )
}
