// @src/components/Modal.jsx

import React from "react";
import styles from "./index.module.scss";
import { RiCloseLine } from "react-icons/ri";

export function Modal(props) {
  return (
    <>
      <div className={styles.dark_bg} onClick={() => props.setIsOpen(false)} />
      <div className={styles.centered}>
        <div className={styles.modal}>
          <div className={styles.modal_header}>
            <h5 className={styles.heading}>{props.heading}</h5>
          </div>
          <button className={styles.close_btn} onClick={() => props.setIsOpen(false)}>
            <RiCloseLine style={{ marginBottom: "-3px" }} />
          </button>
          <div className={styles.modal_content}>
            {props.content}
          </div>
          <div className={styles.modal_actions}>
            <div className={styles.actions_container}>
              <button
                className={styles.delete_btn}
                onClick={() => props.setIsOpen(false)}
              >
                Delete
              </button>
              <button
                className={styles.cancel_btn}
                onClick={() => props.setIsOpen(false)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

/** 
 * Example usage:
 * import { Modal } from "@components/Modal/custom";
 * const [isOpen, setIsOpen] = useState(false);
 * <Button
      text="Open Modal"
      color="#185adb"
      onClick={() => setIsOpen(true)}
      shadow="0 10px 20px -10px rgba(24, 90, 219, 0.6)"
    />
    {isOpen && (
      <Modal
        heading="Welcome"
        content="This is a test"
        setIsOpen={setIsOpen}
      />
    )}
 * 
 * 
*/
