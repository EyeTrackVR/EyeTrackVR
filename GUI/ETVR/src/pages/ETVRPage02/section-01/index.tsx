import useWindowSize from "@rehooks/window-size";
import { gsap } from "gsap/all";
import { useEffect, useRef, useState } from "react";

export function Section01(props) {
  useEffect(() => {
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
  }, [useWindowSize().innerWidth]);

  return (
    <>
    </>
  );
}
