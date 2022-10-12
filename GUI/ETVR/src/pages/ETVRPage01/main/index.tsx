/* eslint-disable @typescript-eslint/no-explicit-any */

/* import useWindowSize from "@rehooks/window-size";
import { gsap } from "gsap/all"; */
import { Button } from "@src/components/Buttons";
import { MainMenu } from "@src/components/MainMenu";
/* import React, { useEffect, useRef, useState } from "react"; */
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
    const centerStyle: any = {
        position: "absolute",
        top: "50%",
        left: "50%",
        transform: "translate(-50%, -50%)",
        zIndex: 1000,
    };
    return (
        <>
            <MainMenu />
            <main>
                <div style={centerStyle}>
                    <Button
                        text="Log"
                        color="#6f4ca1"
                        onClick={() => console.log("clicked")}
                        shadow="0 10px 20px -10px rgba(24, 90, 219, 0.6)"
                    />
                </div>
            </main>
        </>
    );
}
