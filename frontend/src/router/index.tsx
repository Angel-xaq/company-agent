import { useEffect, type ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'

import Layout from '@/layouts/Layout'
import Home from '@/views/Home'
import Profile from '@/views/Profile'
import Password from '@/views/auth/Password'
import Login from '@/views/auth/Login'
import Register from '@/views/auth/Register'
import { useUser } from '@/store/UserContext'
import { getToken } from '@/utils/auth'
import { feedback } from '@/utils/feedback'

/** 白名单：不依赖菜单绑定即可访问 */
const WHITE_LIST = ['/manager/home', '/manager/profile', '/manager/password']

/** 登录态守卫：未登录跳转登录页 */
function RequireAuth({ children }: { children: ReactNode }) {
  const location = useLocation()
  if (!getToken()) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <>{children}</>
}

/** 游客守卫：已登录用户不再进入登录/注册页 */
function GuestOnly({ children }: { children: ReactNode }) {
  if (getToken()) {
    return <Navigate to="/manager/home" replace />
  }
  return <>{children}</>
}

/** 菜单权限守卫：非白名单页面须出现在当前用户菜单树中 */
function MenuAccessGuard({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  const { menus, getMenuPaths } = useUser()

  const allowed =
    WHITE_LIST.includes(pathname) || menus.length === 0 || getMenuPaths().includes(pathname)

  useEffect(() => {
    if (!allowed) {
      feedback.warning('无权限访问该页面')
    }
  }, [allowed])

  if (!allowed) {
    return <Navigate to="/manager/home" replace />
  }
  return <>{children}</>
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/manager/home" replace />} />

      <Route
        path="/login"
        element={
          <GuestOnly>
            <Login />
          </GuestOnly>
        }
      />
      <Route
        path="/register"
        element={
          <GuestOnly>
            <Register />
          </GuestOnly>
        }
      />

      <Route
        path="/manager"
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/manager/home" replace />} />
        <Route path="home" element={<Home />} />
        <Route
          path="profile"
          element={
            <MenuAccessGuard>
              <Profile />
            </MenuAccessGuard>
          }
        />
        <Route
          path="password"
          element={
            <MenuAccessGuard>
              <Password />
            </MenuAccessGuard>
          }
        />
      </Route>

      <Route path="*" element={<Navigate to="/manager/home" replace />} />
    </Routes>
  )
}
