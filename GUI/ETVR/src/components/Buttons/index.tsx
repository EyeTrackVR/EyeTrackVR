import styles from './index.module.scss'

export interface Iprops {
  color: string
  text: string
  shadow: string
  onClick: () => void
}

export const Button = (props: Iprops) => {
  return (
    <button
      className={styles.primary_btn}
      style={{ background: props.color, boxShadow: props.shadow }}
      onClick={props.onClick}>
      {props.text}
    </button>
  )
}
