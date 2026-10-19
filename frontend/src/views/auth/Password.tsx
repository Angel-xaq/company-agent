import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Form, Input } from 'antd'

import { updatePasswordApi } from '@/api/user'
import { logout } from '@/utils/auth'
import { feedback } from '@/utils/feedback'

interface PasswordForm {
  oldPassword: string
  newPassword: string
  confirmPassword: string
}

export default function Password() {
  const [form] = Form.useForm<PasswordForm>()
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()

  async function handleFinish(values: PasswordForm) {
    setSubmitting(true)
    try {
      await updatePasswordApi({
        old_password: values.oldPassword,
        new_password: values.newPassword
      })
      feedback.success('密码修改成功，请重新登录')
      logout()
      navigate('/login', { replace: true })
    } catch {
      // 错误提示已由 axios 拦截器统一处理
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page-narrow">
      <Card title="修改密码" variant="borderless">
        <Form<PasswordForm>
          form={form}
          onFinish={handleFinish}
          labelCol={{ span: 5 }}
          wrapperCol={{ span: 19 }}
          style={{ maxWidth: 480 }}
        >
          <Form.Item
            label="原密码"
            name="oldPassword"
            rules={[{ required: true, message: '请输入原密码' }]}
          >
            <Input.Password placeholder="请输入原密码" autoComplete="current-password" />
          </Form.Item>
          <Form.Item
            label="新密码"
            name="newPassword"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 6, max: 64, message: '密码长度为 6-64 位' }
            ]}
          >
            <Input.Password placeholder="请输入新密码" autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            label="确认密码"
            name="confirmPassword"
            dependencies={['newPassword']}
            rules={[
              { required: true, message: '请确认密码' },
              ({ getFieldValue }) => ({
                validator(_, value: string) {
                  if (!value || getFieldValue('newPassword') === value) {
                    return Promise.resolve()
                  }
                  return Promise.reject(new Error('两次密码输入不一致'))
                }
              })
            ]}
          >
            <Input.Password placeholder="请再次输入新密码" autoComplete="new-password" />
          </Form.Item>
          <Form.Item wrapperCol={{ offset: 5, span: 19 }} style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" loading={submitting}>
              确认修改
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
