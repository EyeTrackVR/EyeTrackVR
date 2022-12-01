import { Provider } from 'react-redux'
import { Outlet } from 'react-router-dom'
import AppRoutes from './pages/routes/Routes'
import store from './redux'

export default function App() {
  return (
    <div className="App">
      <Provider store={store}>
        <AppRoutes />
        <Outlet />
      </Provider>
    </div>
  )
}
