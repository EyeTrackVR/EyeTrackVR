/* eslint-disable */
import Header from '@components/Header'
import { customUseSelector, IExample } from '@redux/Selectors/exampleSelector'
import { actions } from '@redux/reducers/example'
import { useEffect } from 'react'
import { useDispatch } from 'react-redux'

import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { routes } from '.'
// TODO: Add autodetection component that chooses between the one eye and two eye modes based on the number of cameras connected
// TODO: Implement a settings page that allows the user to change the settings of the application

export default function AppRoutes() {
  const fetchDataExample = customUseSelector(({ ui }: IExample) => ui)

  const dispatch = useDispatch()
  const getUserName = () => {
    const userName = localStorage.getItem('settings')
    if (typeof userName === 'string') {
      const parsedItem = JSON.parse(userName) // ok
      return parsedItem
    }
    return ''
  }

  useEffect(() => {
    //default request
    dispatch(actions.setExample(true))

    //saga request
    dispatch(actions.requestSagaExample({ status: true }))

    console.log(fetchDataExample)
  }, [dispatch, fetchDataExample])

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
