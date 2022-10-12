/* eslint-disable @typescript-eslint/no-non-null-assertion */
// @src/components/Modal.jsx

import React from "react";
import ReactDom from "react-dom";
import { RiCloseLine } from "react-icons/ri";
import styles from "./index.module.scss";

const portalDiv = document.getElementById("#portal")!;

export function Modal(props) {
    if (!props.state) return null;
    return ReactDom.createPortal(
        <>
            <div
                className={styles.dark_bg}
                onClick={() => props.setIsOpen(false)}
            />
            <div className={styles.centered}>
                <div className={styles.modal}>
                    <div className={styles.modal_header}>
                        <h5 className={styles.heading}>{props.heading}</h5>
                    </div>
                    <button
                        className={styles.close_btn}
                        onClick={() => props.setIsOpen(false)}
                    >
                        <RiCloseLine style={{ marginBottom: "-3px" }} />
                    </button>
                    <div className={styles.modal_content}>{props.content}</div>
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
        </>,
        portalDiv
    );
}

/** 
 * Example usage:
 * import { Modal } from "@components/Modal";
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
