import { Outlet } from 'react-router-dom'
import AppRoutes from './pages/routes/Routes'

export default function App() {
  return (
    <div className="App">
      <AppRoutes />
      <Outlet />
    </div>
  )
}
