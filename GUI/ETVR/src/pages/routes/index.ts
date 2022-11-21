import { SettingsPage } from '@components/Settings'
import Main from '@pages/Home'
export interface IRoutes {
  path: string
  index: string
  element: () => JSX.Element
}

export const routes: IRoutes[] = [
  { path: '/', element: Main, index: 'main' },
  { path: '/settings', element: SettingsPage, index: 'settings_page' },
]
