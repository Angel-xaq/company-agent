import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Avatar, Dropdown, Layout as AntLayout, Menu, type MenuProps } from 'antd'
import {
  ApiOutlined,
  AppstoreOutlined,
  CommentOutlined,
  DownOutlined,
  FileDoneOutlined,
  HomeOutlined,
  IdcardOutlined,
  LockOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuOutlined,
  MenuUnfoldOutlined,
  ProfileOutlined,
  RobotOutlined,
  SettingOutlined,
  TeamOutlined,
  UserOutlined
} from '@ant-design/icons'

import { useUser } from '@/store/UserContext'
import { logout } from '@/utils/auth'
import type { MenuNode } from '@/types'

const { Header, Sider, Content } = AntLayout

const COLLAPSE_KEY = 'lab-sidebar-collapsed'
const ASIDE_EXPANDED = 220
const ASIDE_COLLAPSED = 64
const HOME_PATH = '/manager/home'

/** Element Plus 图标名 -> Ant Design 图标，兼容后端已有菜单数据 */
const iconMap: Record<string, ReactNode> = {
  Menu: <MenuOutlined />,
  House: <HomeOutlined />,
  HomeFilled: <HomeOutlined />,
  Setting: <SettingOutlined />,
  User: <UserOutlined />,
  Avatar: <UserOutlined />,
  OfficeBuilding: <TeamOutlined />,
  Tickets: <ProfileOutlined />,
  DocumentChecked: <FileDoneOutlined />,
  ChatDotRound: <CommentOutlined />,
  Grid: <AppstoreOutlined />,
  Cpu: <ApiOutlined />
}

/** 按菜单 icon 名解析为 Ant Design 图标 */
function resolveIcon(name?: string | null): ReactNode {
  if (!name) return <MenuOutlined />
  return iconMap[name] ?? <MenuOutlined />
}

/** 侧栏只展示 visible !== 0 的菜单 */
function filterVisible(list: MenuNode[]): MenuNode[] {
  return list
    .filter((item) => item.visible !== 0)
    .map((item) => ({
      ...item,
      children: item.children ? filterVisible(item.children) : []
    }))
}

/** 菜单树转为 antd Menu items */
function toMenuItems(list: MenuNode[]): NonNullable<MenuProps['items']> {
  return list.map((item) => {
    const key = item.path || `menu-${item.id}`
    const icon = resolveIcon(item.icon)
    if (item.children?.length) {
      return {
        key,
        icon,
        label: item.name,
        children: toMenuItems(item.children)
      }
    }
    return {
      key,
      icon,
      label: item.name,
      disabled: !item.path
    }
  })
}

/** 菜单树中是否包含指定 path */
function hasPath(list: MenuNode[], path: string): boolean {
  return list.some(
    (item) => item.path === path || (item.children?.length ? hasPath(item.children, path) : false)
  )
}

export default function Layout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { userInfo, menus, loadMenus } = useUser()

  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(COLLAPSE_KEY) === '1'
  )

  const sidebarMenus = useMemo(() => filterVisible(menus), [menus])

  const menuItems = useMemo<MenuProps['items']>(() => {
    const items = toMenuItems(sidebarMenus)
    if (!hasPath(sidebarMenus, HOME_PATH)) {
      items.unshift({ key: HOME_PATH, icon: <HomeOutlined />, label: '首页' })
    }
    return items
  }, [sidebarMenus])

  const dropdownItems = useMemo<MenuProps['items']>(
    () => [
      { key: 'profile', icon: <IdcardOutlined />, label: '个人信息' },
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
    if (key === 'profile') {
      navigate('/manager/profile')
    } else if (key === 'password') {
      navigate('/manager/password')
    } else if (key === 'logout') {
      logout()
      navigate('/login', { replace: true })
    }
  }

  useEffect(() => {
    void loadMenus()
  }, [loadMenus])

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
              items={menuItems}
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
