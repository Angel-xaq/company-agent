import type { ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'

import Layout from '@/layouts/Layout'
import Chat from '@/views/chat/Chat'
import RoomBoard from '@/views/rooms/RoomBoard'
import MyBookings from '@/views/bookings/MyBookings'
import Knowledge from '@/views/knowledge/Knowledge'
import Password from '@/views/auth/Password'
import Login from '@/views/auth/Login'
import Register from '@/views/auth/Register'
import { getToken } from '@/utils/auth'

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
    return <Navigate to="/manager/chat" replace />
  }
  return <>{children}</>
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/manager/chat" replace />} />

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
        <Route index element={<Navigate to="/manager/chat" replace />} />
        <Route path="home" element={<Navigate to="/manager/chat" replace />} />
        <Route path="chat" element={<Chat />} />
        <Route path="rooms" element={<RoomBoard />} />
        <Route path="bookings" element={<MyBookings />} />
        <Route path="knowledge" element={<Knowledge />} />
        <Route path="password" element={<Password />} />
      </Route>

      <Route path="*" element={<Navigate to="/manager/chat" replace />} />
    </Routes>
  )
}
