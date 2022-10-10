import { Logo } from "@src/components/Logo";
import { Greeting } from "@src/components/Greeting";
import styles from "./index.module.scss";

const NavbarLinks = ["cameras", "settings"];

export function MainMenu() {
  return (
    <>
      <div className={styles.main_menu}>
        <Logo />
        <div className={styles.navbar_container}>
          <nav className={styles.navbar_group}>
            <div className={styles.rectangle_2}></div>
            <div className={styles.active}>cameras</div>
          </nav>
        </div>
        <div className={styles.rectangle_146}>
          <Greeting />
        </div>
      </div>
    </>
  );
}
