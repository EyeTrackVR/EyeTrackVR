/* eslint-disable @typescript-eslint/no-explicit-any */
import { Button } from "@src/components/Buttons";
import styles from "./index.module.scss";

export function Settings() {
    /* const centerStyle: any = {
        position: "absolute",
        top: "50%",
        left: "50%",
        transform: "translate(-50%, -50%)",
        zIndex: 1000,
    }; */

    return (
        <div className={styles.settings_main}>
            <div /* style={centerStyle} */>
                <Button
                    text="Log"
                    color="#6f4ca1"
                    onClick={() => console.log("clicked")}
                    shadow="0 10px 20px -10px rgba(24, 90, 219, 0.6)"
                />
            </div>
        </div>
    );
}
