import Header from '@components/Header'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { routes } from '.'

// TODO: Add autodetection component that chooses between the one eye and two eye modes based on the number of cameras connected
// TODO: Implement a settings page that allows the user to change the settings of the application

export default function AppRoutes() {
  const getUserName = () => {
    const userName = localStorage.getItem('settings')
    if (typeof userName === 'string') {
      const parsedItem = JSON.parse(userName) // ok
      return parsedItem
    }
    return ''
  }
  return (
    <BrowserRouter>
      <Header name={getUserName()['name'] ? `Welcome ${getUserName()['name']}` : 'Welcome!'} />
      <Routes>
        {routes.map(({ index, path, element }) => (
          <Route key={index} path={path} element={element()} />
        ))}
      </Routes>
    </BrowserRouter>
  )
}
