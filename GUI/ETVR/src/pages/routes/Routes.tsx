import Header from '@components/Header'

import config from '@tauri/config/config.json'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { routes } from '.'

// TODO: Add autodetection component that chooses between the one eye and two eye modes based on the number of cameras connected
// TODO: Implement a settings page that allows the user to change the settings of the application

export default function AppRoutes() {
  return (
    <BrowserRouter>
      <Header name={config.name ? `welcome ${config.name}` : '!'} />
      <Routes>
        {routes.map(({ path, element }) => (
          <Route path={path} element={element()} />
        ))}
      </Routes>
    </BrowserRouter>
  )
}
