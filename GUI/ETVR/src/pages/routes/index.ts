import { SettingsPage } from '@components/Settings'
import Main from '@pages/Home'
export interface IRoutes {
  path: string
  element: () => JSX.Element
}

export const routes: IRoutes[] = [
  { path: '/', element: Main },
  { path: '/settings', element: SettingsPage },
]
