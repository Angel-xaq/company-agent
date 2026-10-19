import { useEffect, useState } from 'react'
import { Button, Card, Form, Input } from 'antd'

import { getMeApi, updateMeApi, type UpdateProfileParams } from '@/api/user'
import { useUser } from '@/store/UserContext'
import { feedback } from '@/utils/feedback'

interface ProfileForm extends UpdateProfileParams {
  username: string
}

export default function Profile() {
  const [form] = Form.useForm<ProfileForm>()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const { updateUser } = useUser()

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      try {
        const res = await getMeApi()
        if (cancelled) return
        form.setFieldsValue({
          username: res.data.username,
          name: res.data.name,
          email: res.data.email ?? '',
          phone: res.data.phone ?? '',
          avatar: res.data.avatar ?? ''
        })
        updateUser(res.data)
      } catch {
        // 错误提示已由 axios 拦截器统一处理
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [form, updateUser])

  async function handleFinish(values: ProfileForm) {
    setSaving(true)
    try {
      const res = await updateMeApi({
        name: values.name,
        email: values.email || undefined,
        phone: values.phone || undefined,
        avatar: values.avatar || undefined
      })
      updateUser(res.data)
      feedback.success('保存成功')
    } catch {
      // 错误提示已由 axios 拦截器统一处理
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="page-narrow">
      <Card title="个人信息" variant="borderless" loading={loading}>
        <Form<ProfileForm>
          form={form}
          onFinish={handleFinish}
          labelCol={{ span: 5 }}
          wrapperCol={{ span: 19 }}
          style={{ maxWidth: 520 }}
        >
          <Form.Item label="账号" name="username">
            <Input disabled />
          </Form.Item>
          <Form.Item
            label="姓名"
            name="name"
            rules={[{ required: true, message: '请输入姓名' }]}
          >
            <Input placeholder="请输入姓名" />
          </Form.Item>
          <Form.Item
            label="邮箱"
            name="email"
            rules={[{ type: 'email', message: '请输入正确的邮箱地址' }]}
          >
            <Input placeholder="请输入邮箱" />
          </Form.Item>
          <Form.Item label="手机号" name="phone">
            <Input placeholder="请输入手机号" />
          </Form.Item>
          <Form.Item label="头像地址" name="avatar">
            <Input placeholder="请输入头像图片地址，如 /uploads/avatar.png" />
          </Form.Item>
          <Form.Item wrapperCol={{ offset: 5, span: 19 }} style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" loading={saving}>
              保存修改
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
