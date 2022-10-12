import etvrLogo from "/images/logo.png";
import styles from "./index.module.scss";

export function Logo() {
    return (
        <div className={styles.eyetrackvr_logo_gif_1}>
            <div className={styles.eyetrackvr_logo_gif_1_image}>
                <img
                    src={etvrLogo}
                    alt="eytrackvrlogo"
                    height="90px"
                    width="90px"
                />
                <p className={styles.notifications_div}>4</p>
            </div>
        </div>
    );
}
