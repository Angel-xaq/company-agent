import { useMemo, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Avatar, Dropdown, Layout as AntLayout, Menu, type MenuProps } from 'antd'
import {
  BookOutlined,
  CalendarOutlined,
  CommentOutlined,
  DownOutlined,
  LockOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  RobotOutlined,
  TeamOutlined,
  UserOutlined
} from '@ant-design/icons'

import { useUser } from '@/store/UserContext'
import { logout } from '@/utils/auth'

const { Header, Sider, Content } = AntLayout

const COLLAPSE_KEY = 'lab-sidebar-collapsed'
const ASIDE_EXPANDED = 220
const ASIDE_COLLAPSED = 64

/** 侧边栏对所有登录用户一致，不做菜单级权限过滤 */
const APP_MENU_ITEMS: NonNullable<MenuProps['items']> = [
  { key: '/manager/chat', icon: <CommentOutlined />, label: '智能对话' },
  { key: '/manager/rooms', icon: <TeamOutlined />, label: '会议室看板' },
  { key: '/manager/bookings', icon: <CalendarOutlined />, label: '我的预约' },
  { key: '/manager/knowledge', icon: <BookOutlined />, label: '知识库' }
]

export default function Layout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { userInfo } = useUser()

  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(COLLAPSE_KEY) === '1'
  )

  const dropdownItems = useMemo<MenuProps['items']>(
    () => [
      { key: 'password', icon: <LockOutlined />, label: '修改密码' },
      { type: 'divider' },
      { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', danger: true }
    ],
    []
  )

  /** 切换侧栏折叠并持久化 */
  function toggleCollapse() {
    setCollapsed((prev) => {
      const next = !prev
      localStorage.setItem(COLLAPSE_KEY, next ? '1' : '0')
      return next
    })
  }

  function handleMenuClick({ key }: { key: string }) {
    if (key.startsWith('/')) {
      navigate(key)
    }
  }

  function handleUserMenuClick({ key }: { key: string }) {
    if (key === 'password') {
      navigate('/manager/password')
    } else if (key === 'logout') {
      logout()
      navigate('/login', { replace: true })
    }
  }

  return (
    <AntLayout className="app-shell">
      <Header className="app-header">
        <div className="brand">
          <RobotOutlined className="brand-icon" />
          <span>公司智能管理系统</span>
        </div>
        <Dropdown
          menu={{ items: dropdownItems, onClick: handleUserMenuClick }}
          placement="bottomRight"
          trigger={['click']}
        >
          <div className="user-chip">
            <Avatar
              size={36}
              src={userInfo?.avatar || undefined}
              icon={<UserOutlined />}
            />
            <span className="user-name">{userInfo?.name || userInfo?.username || '未登录'}</span>
            <DownOutlined className="user-arrow" />
          </div>
        </Dropdown>
      </Header>
      <AntLayout>
        <Sider
          className="app-sider"
          theme="light"
          width={ASIDE_EXPANDED}
          collapsedWidth={ASIDE_COLLAPSED}
          collapsed={collapsed}
          trigger={null}
        >
          <div className="sider-inner">
            <Menu
              mode="inline"
              items={APP_MENU_ITEMS}
              selectedKeys={[location.pathname]}
              onClick={handleMenuClick}
              inlineCollapsed={collapsed}
              style={{ borderInlineEnd: 'none' }}
            />
            <button
              type="button"
              className="collapse-btn"
              title={collapsed ? '展开菜单' : '收起菜单'}
              onClick={toggleCollapse}
            >
              {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              {!collapsed && <span>收起菜单</span>}
            </button>
          </div>
        </Sider>
        <Content className="app-content">
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  )
}
