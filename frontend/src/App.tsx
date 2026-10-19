import { BrowserRouter } from 'react-router-dom'

import AppRoutes from '@/router'
import { UserProvider } from '@/store/UserContext'

export default function App() {
  return (
    <UserProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </UserProvider>
  )
}
