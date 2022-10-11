import * as React from "react";
import { Logo } from "@src/components/Logo";
import { Greeting } from "@src/components/Greeting";
import styles from "./index.module.scss";

/* function mapping() {
  const navbarLinks = ["cameras", "settings"];
  const map = navbarLinks.map((i) => {
    return (
      <div className={styles.navbar_links}>
        <span>{i}</span>
      </div>
    );
  });
  return map;
} */

export function MainMenu() {
  const [state, setState] = React.useState({
    dashboard: true,
    settings: false
  });

  const handleNavChange = (event) => {
    setState({
      ...state,
      dashboard: !state.dashboard,
      settings: !state.settings
    });
    console.log(event.currentTarget);
  };

  return (
    <>
      <div className={styles.main_menu}>
        <Logo />
        <div className={styles.navbar_container}>
          <div className={styles.navbar_group}>
            <div onClick={handleNavChange} className={styles.navbar_item}>
              <div
                className={
                  state.dashboard
                    ? styles.dashboard_highlight
                    : styles.highlight_inactive
                }
              ></div>
              <div
                className={state.dashboard ? styles.nav_item_active : styles.nav_item_inactive}
              >
                <span>dashboard</span>
                {/* Dashboard Goes here */}
              </div>
            </div>
          </div>
          <div className={styles.navbar_group}>
            <div onClick={handleNavChange} className={styles.navbar_item}>
              <div
                className={
                  state.settings
                    ? styles.settings_highlight
                    : styles.highlight_inactive
                }
              ></div>
              <div className={state.settings ? styles.nav_item_active : styles.nav_item_inactive}>
                <span>settings</span>
                {/* Settings Goes here */}
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
