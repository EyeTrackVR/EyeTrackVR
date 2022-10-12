/* eslint-disable @typescript-eslint/no-non-null-assertion */
/* eslint-disable @typescript-eslint/no-explicit-any */

/* import useWindowSize from "@rehooks/window-size";
import { gsap } from "gsap/all"; */
import { DashBoard } from "@src/components/Dashboard";
import { MainMenu } from "@src/components/MainMenu";
import { Settings } from "@src/components/Settings";
import * as React from "react";
/* import styles from "./index.module.scss"; */

export function Main(/* props */) {
    /* useEffect(() => {
    let tl = gsap.timeline();
    tl.from(".text1", { y: 50, duration: 3, opacity: 0, ease: "power3.inOut" });
  }, []);
  const bgRef: any = useRef(null);
  const isSmall = useWindowSize().innerWidth < 900;
  // get height of background image
  const [bgHeight, setBgHeight] = useState(0);

  function setSectionHeightOfBackground() {
    const bgHeight = bgRef?.current?.clientHeight;
    if (bgHeight) {
      setBgHeight(bgHeight + 80);
    } else {
      setTimeout(() => {
        setSectionHeightOfBackground();
      }, 50);
    }
  }

  useEffect(() => {
    // sleep for 1 second

    setSectionHeightOfBackground();
  }, []);

  useEffect(() => {
    if (bgRef?.current) {
      window.getComputedStyle(bgRef.current);
      setBgHeight(bgRef.current?.offsetHeight);
    }
  }, [useWindowSize().innerWidth]); */

    const [navState, setNavState] = React.useState({
        dashboard: true,
        settings: false,
    });

    const handleNavChange = (/* event */) => {
        setNavState({
            ...navState,
            dashboard: !navState.dashboard,
            settings: !navState.settings,
        });
        /* console.log(event.currentTarget); */
    };

    return (
        <>
            <MainMenu handleNavChange={handleNavChange} state={navState}/>
            <main>{navState.dashboard ? <DashBoard /> : <Settings />}</main>
        </>
    );
}
