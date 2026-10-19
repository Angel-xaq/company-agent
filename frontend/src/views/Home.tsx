import { Card, Col, Empty, Row, Space, Tag, Typography } from 'antd'

import { useUser } from '@/store/UserContext'

export default function Home() {
  const { userInfo, permissions } = useUser()

  const roleLabel = userInfo?.roles?.length
    ? userInfo.roles.map((role) => role.name).join(' / ')
    : userInfo?.role || '访客'

  return (
    <div className="page-stack">
      <Card variant="borderless">
        <Typography.Title level={4} style={{ marginTop: 0 }}>
          你好，{userInfo?.name || userInfo?.username || '同学'}
        </Typography.Title>
        <Typography.Text type="secondary">
          欢迎使用公司智能管理系统 · 当前身份：{roleLabel}
        </Typography.Text>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card title="我的角色" variant="borderless">
            {userInfo?.roles?.length ? (
              <Space wrap>
                {userInfo.roles.map((role) => (
                  <Tag color="blue" key={role.id}>
                    {role.name}（{role.code}）
                  </Tag>
                ))}
              </Space>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无角色" />
            )}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title="可用权限" variant="borderless">
            {permissions.length ? (
              <Space wrap>
                {permissions.map((code) => (
                  <Tag key={code}>{code}</Tag>
                ))}
              </Space>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无权限" />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
