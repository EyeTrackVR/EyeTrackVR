import styles from './index.module.scss'

export function Button(props) {
  return (
    <button
      className={styles.primary_btn}
      style={{ background: props.color, boxShadow: props.shadow }}
      onClick={props.onClick}>
      {props.text}
    </button>
  )
}
