import { Button } from '@src/components/Buttons'
import styles from './index.module.scss'

export function Settings() {
  return (
    <div className={styles.settings_main}>
      <div>
        <Button
          text="Log"
          color="#6f4ca1"
          onClick={() => console.log('clicked')}
          shadow="0 10px 20px -10px rgba(24, 90, 219, 0.6)"
        />
      </div>
    </div>
  )
}
