import { Greeting } from "@src/components/Greeting";
import { Logo } from "@src/components/Logo";
import styles from "./index.module.scss";

export function MainMenu({ handleNavChange, state }) {
    return (
        <>
            <div className={styles.main_menu}>
                <Logo />
                <div className={styles.navbar_container}>
                    <div className={styles.navbar_group}>
                        <div
                            onClick={handleNavChange}
                            className={styles.navbar_item}
                        >
                            <div
                                className={
                                    state.dashboard
                                        ? styles.dashboard_highlight
                                        : styles.highlight_inactive
                                }
                            />
                            <div
                                className={
                                    state.dashboard
                                        ? styles.nav_item_active
                                        : styles.nav_item_inactive
                                }
                            >
                                <span>dashboard</span>
                            </div>
                        </div>
                    </div>
                    <div className={styles.navbar_group}>
                        <div
                            onClick={handleNavChange}
                            className={styles.navbar_item}
                        >
                            <div
                                className={
                                    state.settings
                                        ? styles.settings_highlight
                                        : styles.highlight_inactive
                                }
                            />
                            <div
                                className={
                                    state.settings
                                        ? styles.nav_item_active
                                        : styles.nav_item_inactive
                                }
                            >
                                <span>settings</span>
                            </div>
                        </div>
                    </div>
                </div>
                <div className={styles.rectangle_146}>
                    <Greeting />
                </div>
            </div>
        </>
    );
}
