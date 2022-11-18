import reportWebVitals from '@assets/js/reportWebVitals'
import { invoke } from '@tauri-apps/api/tauri'
import config from '@tauri/config/config.json'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@src/styles/imports.css'
import App from './App'

document.addEventListener('DOMContentLoaded', () => {
  if (!config.name) {
    invoke('get_user').then((config) => {
      console.log(config)
    })
  }
  setTimeout(() => invoke('close_splashscreen'), 3000)
})

const root = createRoot(document.getElementById('root') as HTMLElement)

declare global {
  namespace JSX {
    interface IntrinsicElements {
      item: React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement>
    }
  }
}

root.render(
  <StrictMode>
    <App />
  </StrictMode>
)

reportWebVitals(console.table)
