import { Outlet } from 'react-router-dom'
import AppRoutes from './pages/routes/Routes'

export default function App() {
  return (
    <main className="App">
      <AppRoutes />
      <Outlet />
    </main>
  )
}
