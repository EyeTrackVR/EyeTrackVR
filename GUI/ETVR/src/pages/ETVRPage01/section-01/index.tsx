import useWindowSize from "@rehooks/window-size";
import { gsap } from "gsap/all";
import { useEffect, useRef, useState } from "react";
import { Caresol } from "../caresol";

import.meta.domain_url = {
  PUBLIC_URL: "ETVR-Website"
};

var end_point = import.meta.domain_url.PUBLIC_URL;

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
      <div id="siteWrapper" className="clearfix site-wrapper">
        <div id="floatingCart" className="floating-cart hidden">
          <a
            href="/cart"
            className="icon icon--stroke icon--fill icon--cart sqs-custom-cart"
          >
            <span className="Cart-inner">
              <svg className="icon icon--cart" viewBox="0 0 31 24">
                <g className="svg-icon cart-icon--odd">
                  <circle
                    fill="none"
                    strokeMiterlimit={10}
                    cx="22.5"
                    cy="21.5"
                    r={1}
                  />
                  <circle
                    fill="none"
                    strokeMiterlimit={10}
                    cx="9.5"
                    cy="21.5"
                    r={1}
                  />
                  <path
                    fill="none"
                    strokeMiterlimit={10}
                    d="M0,1.5h5c0.6,0,1.1,0.4,1.1,1l1.7,13 c0.1,0.5,0.6,1,1.1,1h15c0.5,0,1.2-0.4,1.4-0.9l3.3-8.1c0.2-0.5-0.1-0.9-0.6-0.9H12"
                  ></path>
                </g>
              </svg>
            </span>
            <div className="legacy-cart icon-cart-quantity">
              <span className="Cart-inner">
                <span className="sqs-cart-quantity">0</span>
              </span>
            </div>
          </a>
        </div>
        <header
          data-test="header"
          id="header"
          className="black-bold header theme-col--primary"
          data-controller="Header"
          data-current-styles='{ "layout": "navRight", "action": { "href": "/", "buttonText": "CONTACT", "newWindow": false }, "showSocial": false, "sectionTheme": "black-bold", "menuOverlayAnimation": "fade", "cartStyle": "cart", "cartText": "Cart", "showEmptyCartState": true, "cartOptions": { "iconType": "stroke-1", "cartBorderShape": "none", "cartBorderStyle": "outline", "cartBorderThickness": { "unit": "px", "value": 1.0 } }, "showButton": false, "showCart": false, "showAccountLogin": true, "headerStyle": "dynamic", "languagePicker": { "enabled": true, "iconEnabled": true, "iconType": "globe", "flagShape": "shiny", "languageFlags": [ ] }, "mobileOptions": { "layout": "logoLeftNavRight", "menuIcon": "doubleLineHamburger", "menuIconOptions": { "style": "tripleLineHamburger", "thickness": { "unit": "px", "value": 3.0 } } }, "dynamicOptions": { "border": { "enabled": false, "position": "allSides", "thickness": { "unit": "px", "value": 4.0 } } }, "solidOptions": { "headerOpacity": { "unit": "%", "value": 100.0 }, "border": { "enabled": false, "position": "allSides", "thickness": { "unit": "px", "value": 4.0 } }, "dropShadow": { "enabled": false, "blur": { "unit": "px", "value": 30.0 }, "spread": { "unit": "px", "value": 0.0 }, "distance": { "unit": "px", "value": 0.0 } }, "blurBackground": { "enabled": false, "blurRadius": { "unit": "px", "value": 12.0 } } }, "gradientOptions": { "gradientType": "faded", "headerOpacity": { "unit": "%", "value": 90.0 }, "border": { "enabled": false, "position": "allSides", "thickness": { "unit": "px", "value": 4.0 } }, "dropShadow": { "enabled": false, "blur": { "unit": "px", "value": 30.0 }, "spread": { "unit": "px", "value": 0.0 }, "distance": { "unit": "px", "value": 0.0 } }, "blurBackground": { "enabled": false, "blurRadius": { "unit": "px", "value": 12.0 } } }, "showPromotedElement": false }'
          data-section-id="header"
          data-header-theme="black-bold"
          data-menu-overlay-theme
          data-header-style="dynamic"
          data-language-picker='{ "enabled": true, "iconEnabled": true, "iconType": "globe", "flagShape": "shiny", "languageFlags": [ ] }'
          data-first-focusable-element
          tabIndex={-1}
          data-controllers-bound="Header"
        >
          <div className="sqs-announcement-bar-dropzone" />
          <div className="header-announcement-bar-wrapper">
            <a
              href="#page"
              tabIndex={1}
              className="header-skip-link sqs-button-element--primary"
            >
              Skip to Content
            </a>
            <div
              className="header-border"
              data-header-style="dynamic"
              data-test="header-border"
              style={{ borderWidth: "0px !important" }}
            />
            <div
              className="header-dropshadow"
              data-header-style="dynamic"
              data-test="header-dropshadow"
              style={{}}
            />
            <div
              className="header-inner container--fluid header-mobile-layout-logo-left-nav-right header-layout-nav-right"
              style={{ padding: 0 }}
              data-test="header-inner"
            >
              {/* Background */}
              <div className="header-background theme-bg--primary" />
              <div
                className="header-display-desktop"
                data-content-field="site-title"
              >
                {/* Social */}
                {/* Title and nav wrapper */}
                <div className="header-title-nav-wrapper">
                  {/* Title */}
                  <div
                    className="header-title preSlide slideIn"
                    data-animation-role="header-element"
                    style={{
                      transitionTimingFunction: "ease",
                      transitionDuration: "0.8s",
                      transitionDelay: "0s"
                    }}
                  >
                    <div className="header-title-logo">
                      <a
                        href={`/${end_point}`}
                        data-animation-role="header-element"
                        className="preSlide slideIn"
                        style={{
                          transitionTimingFunction: "ease",
                          transitionDuration: "0.8s",
                          transitionDelay: "0.00545455s"
                        }}
                      >
                        <img
                          src="//images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/0404931a-4adf-4306-9db0-e86742a62150/logo_Hbat_logo.png?format=1500w"
                          alt="ETVR"
                        />
                      </a>
                    </div>
                  </div>
                  {/* Nav */}
                  <div className="header-nav">
                    <div className="header-nav-wrapper">
                      <nav className="header-nav-list">
                        <div className="header-nav-item header-nav-item--collection">
                          <a
                            href={`/${end_point}/white-papers`}
                            data-animation-role="header-element"
                            className="preSlide slideIn"
                            style={{
                              transitionTimingFunction: "ease",
                              transitionDuration: "0.8s",
                              transitionDelay: "0.0109091s"
                            }}
                          >
                            White Papers
                          </a>
                        </div>
                        <div className="header-nav-item header-nav-item--collection header-nav-item--active header-nav-item--homepage">
                          <a
                            href={`/${end_point}`}
                            data-animation-role="header-element"
                            aria-current="page"
                            className="preSlide slideIn"
                            style={{
                              transitionTimingFunction: "ease",
                              transitionDuration: "0.8s",
                              transitionDelay: "0.0163636s"
                            }}
                          >
                            Home
                          </a>
                        </div>
                      </nav>
                    </div>
                  </div>
                </div>
                {/* Actions */}
                {/* <div className="header-actions header-actions--right">
              <div className="language-picker language-picker-desktop" id="multilingual-language-picker-desktop">
                <div className="current-language">
                  <span className="icon icon--fill">
                    <svg width={19} height={19} viewBox="0 0 19 19" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path fillRule="evenodd" clipRule="evenodd" d="M9.5 18.833C14.4706 18.833 18.5 14.8036 18.5 9.83301C18.5 4.86244 14.4706 0.833008 9.5 0.833008C4.52944 0.833008 0.5 4.86244 0.5 9.83301C0.5 14.8036 4.52944 18.833 9.5 18.833ZM9.91948 16.5409C9.66958 16.8228 9.52553 16.833 9.5 16.833C9.47447 16.833 9.33042 16.8228 9.08052 16.5409C8.83166 16.2602 8.56185 15.797 8.31501 15.1387C7.9028 14.0395 7.60822 12.5409 7.52435 10.833H11.4757C11.3918 12.5409 11.0972 14.0395 10.685 15.1387C10.4381 15.797 10.1683 16.2602 9.91948 16.5409ZM11.4757 8.83301H7.52435C7.60822 7.12511 7.9028 5.62649 8.31501 4.52728C8.56185 3.86902 8.83166 3.40579 9.08052 3.12509C9.33042 2.84323 9.47447 2.83301 9.5 2.83301C9.52553 2.83301 9.66958 2.84323 9.91948 3.12509C10.1683 3.40579 10.4381 3.86902 10.685 4.52728C11.0972 5.62649 11.3918 7.12511 11.4757 8.83301ZM13.4778 10.833C13.3926 12.7428 13.0651 14.4877 12.5576 15.841C12.5122 15.9623 12.4647 16.0817 12.4154 16.1989C14.5362 15.226 16.087 13.2245 16.4291 10.833H13.4778ZM16.4291 8.83301H13.4778C13.3926 6.92322 13.0651 5.17832 12.5576 3.82503C12.5122 3.7037 12.4647 3.58428 12.4154 3.46714C14.5362 4.44001 16.087 6.44155 16.4291 8.83301ZM5.52218 8.83301C5.60742 6.92322 5.93487 5.17832 6.44235 3.82503C6.48785 3.7037 6.53525 3.58428 6.5846 3.46714C4.46378 4.44001 2.91296 6.44155 2.57089 8.83301H5.52218ZM2.57089 10.833C2.91296 13.2245 4.46378 15.226 6.5846 16.1989C6.53525 16.0817 6.48785 15.9623 6.44235 15.841C5.93487 14.4877 5.60742 12.7428 5.52218 10.833H2.57089Z">
                      </path>
                    </svg></span> <span data-wg-notranslate className="current-language-name">English</span>
                </div>
                <div className="language-picker-content" style={{color: 'white'}}>
                </div>
              </div>
              <div className="showOnMobile" />
              <div className="showOnDesktop" />
            </div> */}
                <style
                  dangerouslySetInnerHTML={{
                    __html:
                      "\n                  .top-bun,\n                  .patty,\n                  .bottom-bun {\n                    height: 3px;\n                }\n                "
                  }}
                />
                {/* Burger */}
                <div
                  className="header-burger menu-overlay-has-visible-non-navigation-items no-actions preSlide slideIn"
                  data-animation-role="header-element"
                  style={{
                    transitionTimingFunction: "ease",
                    transitionDuration: "0.8s",
                    transitionDelay: "0.0218182s"
                  }}
                >
                  <button
                    className="header-burger-btn burger"
                    data-test="header-burger"
                  >
                    <span className="js-header-burger-open-title visually-hidden">
                      Open Menu
                    </span>{" "}
                    <span
                      hidden
                      className="js-header-burger-close-title visually-hidden"
                    >
                      Close Menu
                    </span>
                    <div className="burger-box">
                      <div className="burger-inner header-menu-icon-tripleLineHamburger">
                        <div className="top-bun" />
                        <div className="patty" />
                        <div className="bottom-bun" />
                      </div>
                    </div>
                  </button>
                </div>
              </div>
              <div
                className="header-display-mobile"
                data-content-field="site-title"
              >
                {/* Social */}
                {/* Title and nav wrapper */}
                <div className="header-title-nav-wrapper">
                  {/* Title */}
                  <div
                    className="header-title preSlide slideIn"
                    data-animation-role="header-element"
                    style={{
                      transitionTimingFunction: "ease",
                      transitionDuration: "0.8s",
                      transitionDelay: "0.0272727s"
                    }}
                  >
                    <div className="header-title-logo">
                      <a
                        href={`/${end_point}`}
                        data-animation-role="header-element"
                        className="preSlide slideIn"
                        style={{
                          transitionTimingFunction: "ease",
                          transitionDuration: "0.8s",
                          transitionDelay: "0.0327273s"
                        }}
                      >
                        <img
                          src="//images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/0404931a-4adf-4306-9db0-e86742a62150/logo_Hbat_logo.png?format=1500w"
                          alt="ETVR"
                        />
                      </a>
                    </div>
                  </div>
                  {/* Nav */}
                  <div className="header-nav">
                    <div className="header-nav-wrapper">
                      <nav className="header-nav-list">
                        <div className="header-nav-item header-nav-item--collection">
                          <a
                            href={`/${end_point}/white-papers`}
                            data-animation-role="header-element"
                            className="preSlide slideIn"
                            style={{
                              transitionTimingFunction: "ease",
                              transitionDuration: "0.8s",
                              transitionDelay: "0.0381818s"
                            }}
                          >
                            White Papers
                          </a>
                        </div>
                        <div className="header-nav-item header-nav-item--collection header-nav-item--active header-nav-item--homepage">
                          <a
                            href={`/${end_point}`}
                            data-animation-role="header-element"
                            aria-current="page"
                            className="preSlide slideIn"
                            style={{
                              transitionTimingFunction: "ease",
                              transitionDuration: "0.8s",
                              transitionDelay: "0.0436364s"
                            }}
                          >
                            Home
                          </a>
                        </div>
                      </nav>
                    </div>
                  </div>
                </div>
                {/* Actions */}
                {/* <div className="header-actions header-actions--right">
              <div className="language-picker language-picker-desktop" id="multilingual-language-picker-desktop">
                <div className="current-language">
                  <span className="icon icon--fill"><svg width={19} height={19} viewBox="0 0 19 19" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path fillRule="evenodd" clipRule="evenodd" d="M9.5 18.833C14.4706 18.833 18.5 14.8036 18.5 9.83301C18.5 4.86244 14.4706 0.833008 9.5 0.833008C4.52944 0.833008 0.5 4.86244 0.5 9.83301C0.5 14.8036 4.52944 18.833 9.5 18.833ZM9.91948 16.5409C9.66958 16.8228 9.52553 16.833 9.5 16.833C9.47447 16.833 9.33042 16.8228 9.08052 16.5409C8.83166 16.2602 8.56185 15.797 8.31501 15.1387C7.9028 14.0395 7.60822 12.5409 7.52435 10.833H11.4757C11.3918 12.5409 11.0972 14.0395 10.685 15.1387C10.4381 15.797 10.1683 16.2602 9.91948 16.5409ZM11.4757 8.83301H7.52435C7.60822 7.12511 7.9028 5.62649 8.31501 4.52728C8.56185 3.86902 8.83166 3.40579 9.08052 3.12509C9.33042 2.84323 9.47447 2.83301 9.5 2.83301C9.52553 2.83301 9.66958 2.84323 9.91948 3.12509C10.1683 3.40579 10.4381 3.86902 10.685 4.52728C11.0972 5.62649 11.3918 7.12511 11.4757 8.83301ZM13.4778 10.833C13.3926 12.7428 13.0651 14.4877 12.5576 15.841C12.5122 15.9623 12.4647 16.0817 12.4154 16.1989C14.5362 15.226 16.087 13.2245 16.4291 10.833H13.4778ZM16.4291 8.83301H13.4778C13.3926 6.92322 13.0651 5.17832 12.5576 3.82503C12.5122 3.7037 12.4647 3.58428 12.4154 3.46714C14.5362 4.44001 16.087 6.44155 16.4291 8.83301ZM5.52218 8.83301C5.60742 6.92322 5.93487 5.17832 6.44235 3.82503C6.48785 3.7037 6.53525 3.58428 6.5846 3.46714C4.46378 4.44001 2.91296 6.44155 2.57089 8.83301H5.52218ZM2.57089 10.833C2.91296 13.2245 4.46378 15.226 6.5846 16.1989C6.53525 16.0817 6.48785 15.9623 6.44235 15.841C5.93487 14.4877 5.60742 12.7428 5.52218 10.833H2.57089Z">
                      </path>
                    </svg></span> <span data-wg-notranslate className="current-language-name">English</span>
                </div>
                <div className="language-picker-content" />
              </div>
              <div className="showOnMobile" />
              <div className="showOnDesktop" />
            </div> */}
                <style
                  dangerouslySetInnerHTML={{
                    __html:
                      "\n                  .top-bun,\n                  .patty,\n                  .bottom-bun {\n                    height: 3px;\n                }\n                "
                  }}
                />
                {/* Burger */}
                <div
                  className="header-burger menu-overlay-has-visible-non-navigation-items no-actions preSlide slideIn"
                  data-animation-role="header-element"
                  style={{
                    transitionTimingFunction: "ease",
                    transitionDuration: "0.8s",
                    transitionDelay: "0.0490909s"
                  }}
                >
                  <button
                    className="header-burger-btn burger"
                    data-test="header-burger"
                  >
                    <span className="js-header-burger-open-title visually-hidden">
                      Open Menu
                    </span>{" "}
                    <span
                      hidden
                      className="js-header-burger-close-title visually-hidden"
                    >
                      Close Menu
                    </span>
                    <div className="burger-box">
                      <div className="burger-inner header-menu-icon-tripleLineHamburger">
                        <div className="top-bun" />
                        <div className="patty" />
                        <div className="bottom-bun" />
                      </div>
                    </div>
                  </button>
                </div>
              </div>
            </div>
          </div>
          {/* (Mobile) Menu Navigation */}
          <div
            className="header-menu header-menu--folder-list"
            data-current-styles='{ "layout": "navRight", "action": { "href": "/", "buttonText": "CONTACT", "newWindow": false }, "showSocial": false, "sectionTheme": "black-bold", "menuOverlayAnimation": "fade", "cartStyle": "cart", "cartText": "Cart", "showEmptyCartState": true, "cartOptions": { "iconType": "stroke-1", "cartBorderShape": "none", "cartBorderStyle": "outline", "cartBorderThickness": { "unit": "px", "value": 1.0 } }, "showButton": false, "showCart": false, "showAccountLogin": true, "headerStyle": "dynamic", "languagePicker": { "enabled": true, "iconEnabled": true, "iconType": "globe", "flagShape": "shiny", "languageFlags": [ ] }, "mobileOptions": { "layout": "logoLeftNavRight", "menuIcon": "doubleLineHamburger", "menuIconOptions": { "style": "tripleLineHamburger", "thickness": { "unit": "px", "value": 3.0 } } }, "dynamicOptions": { "border": { "enabled": false, "position": "allSides", "thickness": { "unit": "px", "value": 4.0 } } }, "solidOptions": { "headerOpacity": { "unit": "%", "value": 100.0 }, "border": { "enabled": false, "position": "allSides", "thickness": { "unit": "px", "value": 4.0 } }, "dropShadow": { "enabled": false, "blur": { "unit": "px", "value": 30.0 }, "spread": { "unit": "px", "value": 0.0 }, "distance": { "unit": "px", "value": 0.0 } }, "blurBackground": { "enabled": false, "blurRadius": { "unit": "px", "value": 12.0 } } }, "gradientOptions": { "gradientType": "faded", "headerOpacity": { "unit": "%", "value": 90.0 }, "border": { "enabled": false, "position": "allSides", "thickness": { "unit": "px", "value": 4.0 } }, "dropShadow": { "enabled": false, "blur": { "unit": "px", "value": 30.0 }, "spread": { "unit": "px", "value": 0.0 }, "distance": { "unit": "px", "value": 0.0 } }, "blurBackground": { "enabled": false, "blurRadius": { "unit": "px", "value": 12.0 } } }, "showPromotedElement": false }'
            data-section-id="overlay-nav"
            data-show-account-login="true"
            data-test="header-menu"
            style={{ paddingTop: "196.922px" }}
          >
            <div className="header-menu-bg theme-bg--primary" />
            <div className="header-menu-nav">
              <nav className="header-menu-nav-list">
                <div
                  data-folder="root"
                  className="header-menu-nav-folder header-menu-nav-folder--active"
                >
                  {/* Menu Navigation */}
                  <div className="header-menu-nav-folder-content">
                    <div className="container header-menu-nav-item header-menu-nav-item--collection">
                      <a href={`/${end_point}/white-papers`}>
                        <div className="header-menu-nav-item-content">
                          White Papers
                        </div>
                      </a>
                    </div>
                    <div className="container header-menu-nav-item header-menu-nav-item--collection header-menu-nav-item--active header-menu-nav-item--homepage">
                      <a href="/" aria-current="page">
                        <div className="header-menu-nav-item-content">Home</div>
                      </a>
                    </div>
                  </div>
                  <div className="header-menu-actions" />
                  {/* <div className="header-menu-actions language-picker language-picker-mobile">
                <a data-folder-id="language-picker" href="#">
                  <div className="header-menu-nav-item-content current-language">
                    <span className="icon icon--lg icon--fill"><svg width={19} height={19} viewBox="0 0 19 19" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path fillRule="evenodd" clipRule="evenodd" d="M9.5 18.833C14.4706 18.833 18.5 14.8036 18.5 9.83301C18.5 4.86244 14.4706 0.833008 9.5 0.833008C4.52944 0.833008 0.5 4.86244 0.5 9.83301C0.5 14.8036 4.52944 18.833 9.5 18.833ZM9.91948 16.5409C9.66958 16.8228 9.52553 16.833 9.5 16.833C9.47447 16.833 9.33042 16.8228 9.08052 16.5409C8.83166 16.2602 8.56185 15.797 8.31501 15.1387C7.9028 14.0395 7.60822 12.5409 7.52435 10.833H11.4757C11.3918 12.5409 11.0972 14.0395 10.685 15.1387C10.4381 15.797 10.1683 16.2602 9.91948 16.5409ZM11.4757 8.83301H7.52435C7.60822 7.12511 7.9028 5.62649 8.31501 4.52728C8.56185 3.86902 8.83166 3.40579 9.08052 3.12509C9.33042 2.84323 9.47447 2.83301 9.5 2.83301C9.52553 2.83301 9.66958 2.84323 9.91948 3.12509C10.1683 3.40579 10.4381 3.86902 10.685 4.52728C11.0972 5.62649 11.3918 7.12511 11.4757 8.83301ZM13.4778 10.833C13.3926 12.7428 13.0651 14.4877 12.5576 15.841C12.5122 15.9623 12.4647 16.0817 12.4154 16.1989C14.5362 15.226 16.087 13.2245 16.4291 10.833H13.4778ZM16.4291 8.83301H13.4778C13.3926 6.92322 13.0651 5.17832 12.5576 3.82503C12.5122 3.7037 12.4647 3.58428 12.4154 3.46714C14.5362 4.44001 16.087 6.44155 16.4291 8.83301ZM5.52218 8.83301C5.60742 6.92322 5.93487 5.17832 6.44235 3.82503C6.48785 3.7037 6.53525 3.58428 6.5846 3.46714C4.46378 4.44001 2.91296 6.44155 2.57089 8.83301H5.52218ZM2.57089 10.833C2.91296 13.2245 4.46378 15.226 6.5846 16.1989C6.53525 16.0817 6.48785 15.9623 6.44235 15.841C5.93487 14.4877 5.60742 12.7428 5.52218 10.833H2.57089Z">
                        </path>
                      </svg></span> <span data-wg-notranslate className="current-language-name">English</span>
                  </div>
                </a>
              </div> */}
                </div>
                <div
                  id="multilingual-language-picker-mobile"
                  className="header-menu-nav-folder"
                  data-folder="language-picker"
                >
                  <div className="header-menu-nav-folder-content">
                    <div className="header-menu-controls header-menu-nav-item">
                      <a
                        className="header-menu-controls-control header-menu-controls-control--active"
                        data-action="back"
                        href={`/${end_point}`}
                        tabIndex={-1}
                      >
                        <span>Back</span>
                      </a>
                    </div>
                    <div className="language-picker-content"></div>
                  </div>
                </div>
              </nav>
            </div>
          </div>
        </header>
        <main id="page" className="container" role="main">
          <article
            className="sections"
            data-page-sections="613f32525e18f97349cfc9de"
            id="sections"
          >
            <section
              data-test="page-section"
              data-section-theme="black-bold"
              className="page-section layout-engine-section background-width--full-bleed section-height--large content-width--wide horizontal-alignment--left vertical-alignment--middle black-bold"
              data-section-id="615db7f6edf48d173e9a1399"
              data-controller="SectionWrapperController"
              data-current-styles='{ "imageOverlayOpacity": 0.15, "backgroundWidth": "background-width--full-bleed", "sectionHeight": "section-height--large", "customSectionHeight": 85, "horizontalAlignment": "horizontal-alignment--left", "verticalAlignment": "vertical-alignment--middle", "contentWidth": "content-width--wide", "customContentWidth": 100, "sectionTheme": "black-bold", "sectionAnimation": "none", "backgroundMode": "video", "generative": { "type": "images", "seed": 0, "count": 0, "size": 0, "speed": 0, "backgroundColor": { "type": "SITE_PALETTE_COLOR", "sitePaletteColor": { "id": "accent", "alpha": 1.0 } }, "invertColors": false, "noiseIntensity": 0, "noiseScale": 0, "distortionScaleX": 0, "distortionScaleY": 0, "distortionSpeed": 0, "distortionIntensity": 0, "lightIntensity": 0, "lightX": 0, "bevelRotation": 0, "bevelSize": 0, "bevelStrength": 0, "complexity": 0, "cutoff": 0, "isBevelEnabled": false, "isBlurEnabled": false, "scale": 0, "speedMorph": 0, "speedTravel": 0, "steps": 0, "travelDirection": 0, "noiseBias": 0, "animateNoise": false, "distortionComplexity": 0, "distortionDirection": 0, "distortionMorphSpeed": 0, "distortionSeed": 0, "distortionSmoothness": 0, "linearGradientStartColorDistance": 0, "linearGradientEndColorDistance": 0, "linearGradientAngle": 0, "linearGradientAngleMotion": 0, "linearGradientRepeat": 0, "radialGradientRadius": 0, "radialGradientPositionX": 0, "radialGradientPositionY": 0, "radialGradientFollowCursor": false, "radialGradientFollowSpeed": 0, "presetImageKey": "blob2", "imageTint": { "type": "SITE_PALETTE_COLOR", "sitePaletteColor": { "id": "lightAccent", "alpha": 1.0 } }, "imageScale": 3, "imageCount": 35, "patternEnabled": false, "patternColor": { "type": "SITE_PALETTE_COLOR", "sitePaletteColor": { "id": "black", "alpha": 1.0 } }, "patternSize": 16, "patternImageKey": "", "patternOffsetX": 0, "patternOffsetY": 0, "patternSpaceX": 1, "patternSpaceY": 1, "waveEnabled": false, "waveSpeed": 0, "waveComplexity": 0, "waveDepth": 0, "waveShadowDepth": 0, "boxSize": 0.0, "scaleX": 0, "scaleY": 0, "scaleZ": 0, "isMorphEnabled": false, "lightY": 0, "lightZ": 0, "noiseRange": 0, "positionFactor": 0, "scaleFactor": 0, "colorFactor": 0, "sizeVariance": 0, "wobble": 0, "morph": 0, "scrollMovement": 0, "patternScaleX": 0, "patternScaleY": 0, "patternPowerX": 0, "patternPowerY": 0, "patternAmount": 0, "surfaceHeight": 0, "colorStop1": 0, "colorStop2": 0, "colorStop3": 0, "colorStop4": 0, "gradientDistortionX": 0, "gradientDistortionY": 0, "curveX": 0, "curveY": 0, "curveFunnel": 0, "fogIntensity": 0, "repeat": 0, "rotation": 0, "rotationSpeed": 0, "blur": 0, "complexityY": 0, "complexityZ": 0, "amplitudeY": 0, "amplitudeZ": 0, "offset": 0, "lightAngle": 0, "alpha": 0 } }'
              data-current-context='{ "video": { "playbackSpeed": 0.5, "filter": 1, "filterStrength": 0, "zoom": 0, "videoSourceProvider": "native", "nativeVideoContentItem": { "id": "6166cfc1ae12f80798d24209", "recordType": 61, "addedOn": 1634127809568, "updatedOn": 1634127809568, "authorId": "6141c52ef3ca133b0aa7bb6f", "systemDataId": "c4ec0a87-4dc9-4cc4-918a-31c036068fc7", "systemDataVariants": "1920:1080,640:360", "systemDataSourceType": "mp4", "filename": "Markets_Web_V2_02.mp4", "body": null, "likeCount": 0, "commentCount": 0, "publicCommentCount": 0, "commentState": 1, "author": { "id": "6141c52ef3ca133b0aa7bb6f", "displayName": "Laura Lang", "firstName": "Laura", "lastName": "Lang", "avatarUrl": "https://static1.squarespace.com/static/images/6141c52ff30eda74acf2a221", "bio": "", "avatarAssetUrl": "https://static1.squarespace.com/static/images/6141c52ff30eda74acf2a221" }, "contentType": "video/mp4", "structuredContent": { "_type": "SqspHostedVideo", "videoCodec": "h264", "alexandriaUrl": "https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/c4ec0a87-4dc9-4cc4-918a-31c036068fc7/{variant}", "alexandriaLibraryId": "613f323315e7c403d0d6c265", "aspectRatio": 1.7777777777777777, "durationSeconds": 12.245567 }, "videoCodec": "h264", "alexandriaUrl": "https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/c4ec0a87-4dc9-4cc4-918a-31c036068fc7/{variant}", "alexandriaLibraryId": "613f323315e7c403d0d6c265", "aspectRatio": 1.7777777777777777, "durationSeconds": 12.245567, "items": [ ], "pushedServices": { }, "pendingPushedServices": { }, "recordTypeLabel": "sqsp-hosted-video", "originalSize": "1920:1080" } }, "backgroundImageId": null, "backgroundMediaEffect": null, "typeName": "page" }'
              data-animation="none"
              style={{ paddingTop: "196.922px" }}
              data-controllers-bound="SectionWrapperController"
              data-active="true"
            >
              <div className="section-background">
                <div
                  data-controller="VideoBackgroundNative"
                  data-controllers-bound="VideoBackgroundNative"
                >
                  <div
                    className="sqs-video-background-native content-fill"
                    data-config-native-video='{ "id": "6166cfc1ae12f80798d24209", "recordType": 61, "addedOn": 1634127809568, "updatedOn": 1634127809568, "authorId": "6141c52ef3ca133b0aa7bb6f", "systemDataId": "c4ec0a87-4dc9-4cc4-918a-31c036068fc7", "systemDataVariants": "1920:1080,640:360", "systemDataSourceType": "mp4", "filename": "Markets_Web_V2_02.mp4", "body": null, "likeCount": 0, "commentCount": 0, "publicCommentCount": 0, "commentState": 1, "author": { "id": "6141c52ef3ca133b0aa7bb6f", "displayName": "Laura Lang", "firstName": "Laura", "lastName": "Lang", "avatarUrl": "https://static1.squarespace.com/static/images/6141c52ff30eda74acf2a221", "bio": "", "avatarAssetUrl": "https://static1.squarespace.com/static/images/6141c52ff30eda74acf2a221" }, "contentType": "video/mp4", "structuredContent": { "_type": "SqspHostedVideo", "videoCodec": "h264", "alexandriaUrl": "https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/c4ec0a87-4dc9-4cc4-918a-31c036068fc7/{variant}", "alexandriaLibraryId": "613f323315e7c403d0d6c265", "aspectRatio": 1.7777777777777777, "durationSeconds": 12.245567 }, "videoCodec": "h264", "alexandriaUrl": "https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/c4ec0a87-4dc9-4cc4-918a-31c036068fc7/{variant}", "alexandriaLibraryId": "613f323315e7c403d0d6c265", "aspectRatio": 1.7777777777777777, "durationSeconds": 12.245567, "items": [ ], "pushedServices": { }, "pendingPushedServices": { }, "recordTypeLabel": "sqsp-hosted-video", "originalSize": "1920:1080" }'
                    data-config-playback-speed="0.5"
                    data-config-filter={1}
                    data-config-filter-strength={0}
                  >
                    <div className="sqs-video-background-native__video-player video-player video-player--medium video-player--large">
                      <div
                        tabIndex={0}
                        className="plyr plyr--full-ui plyr--video plyr--html5 plyr--pip-supported plyr--playing plyr--hide-controls"
                      >
                        <div className="plyr__controls" style={{}} />
                        <div className="plyr__video-wrapper">
                          <video
                            autoPlay
                            loop
                            muted
                            playsInline
                            src="https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/c4ec0a87-4dc9-4cc4-918a-31c036068fc7/mp4-h264-1920:1080"
                          >
                            <source src="https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/c4ec0a87-4dc9-4cc4-918a-31c036068fc7/mp4-h264-1920:1080" />
                            <source src="https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/c4ec0a87-4dc9-4cc4-918a-31c036068fc7/mp4-h264-640:360" />
                          </video>
                          <div className="plyr__poster" />
                        </div>
                        <div className="plyr__captions" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <div className="content-wrapper" style={{}}>
                <div className="content">
                  <div
                    className="sqs-layout sqs-grid-12 columns-12"
                    data-type="page-section"
                    id="page-section-615db7f6edf48d173e9a1399"
                  >
                    <div className="row sqs-row">
                      <div className="col sqs-col-7 span-7">
                        <div
                          className="sqs-block code-block sqs-block-code"
                          data-block-type={23}
                          id="block-72fb252b4e5ea0c6b0d3"
                        >
                          <div className="sqs-block-content">
                            <h1
                              className="preSlide slideIn"
                              style={{
                                transitionTimingFunction: "ease",
                                transitionDuration: "0.8s",
                                transitionDelay: "0.0545455s"
                              }}
                            >
                              First fuel cell with Solid State integrated
                              Hydrogen Storage. Using water mist for{" "}
                              <span style={{ color: "#FAFF00" }}>
                                clean energy.
                              </span>
                            </h1>
                          </div>
                        </div>
                        <div
                          className="sqs-block button-block sqs-block-button"
                          data-block-type={53}
                          id="block-1dab2c523df7953b4c63"
                        >
                          <div
                            className="sqs-block-content"
                            id="yui_3_17_2_1_1664274854727_244"
                          >
                            <div
                              className="sqs-block-button-container sqs-block-button-container--left preSlide slideIn"
                              data-animation-role="button"
                              data-alignment="left"
                              data-button-size="medium"
                              data-button-type="primary"
                              id="yui_3_17_2_1_1664274854727_243"
                              style={{
                                transitionTimingFunction: "ease",
                                transitionDuration: "0.8s",
                                transitionDelay: "0.06s"
                              }}
                            >
                              <a
                                href="#page-section-613f32525e18f97349cfc9e9"
                                className="sqs-block-button-element--medium sqs-button-element--primary sqs-block-button-element"
                                data-initialized="true"
                              >
                                CONTACT
                              </a>
                            </div>
                          </div>
                        </div>
                      </div>
                      <div className="col sqs-col-5 span-5">
                        <div
                          className="sqs-block spacer-block sqs-block-spacer sized vsize-1"
                          data-block-type={21}
                          id="block-478850bee1ea6913b135"
                        >
                          <div className="sqs-block-content">&nbsp;</div>
                        </div>
                        <div
                          className="sqs-block spacer-block sqs-block-spacer sized vsize-1"
                          data-block-type={21}
                          id="block-a15b630450a0d6592b6a"
                        >
                          <div className="sqs-block-content">&nbsp;</div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </section>
            <section
              data-test="page-section"
              data-section-theme="white-bold"
              className="page-section layout-engine-section background-width--full-bleed section-height--medium content-width--wide horizontal-alignment--left vertical-alignment--middle white-bold"
              data-section-id="61658b0c073f423893f75b29"
              data-controller="SectionWrapperController"
              data-current-styles='{ "imageOverlayOpacity": 0.15, "backgroundWidth": "background-width--full-bleed", "sectionHeight": "section-height--medium", "customSectionHeight": 30, "horizontalAlignment": "horizontal-alignment--left", "verticalAlignment": "vertical-alignment--middle", "contentWidth": "content-width--wide", "sectionTheme": "white-bold", "sectionAnimation": "none", "backgroundMode": "video" }'
              data-current-context='{ "video": { "playbackSpeed": 0.5, "filter": 2, "filterStrength": 0, "zoom": 0, "videoSourceProvider": "none" }, "backgroundImageId": null, "backgroundMediaEffect": null, "typeName": "page" }'
              data-animation="none"
              data-controllers-bound="SectionWrapperController"
              id="yui_3_17_2_1_1664274854727_75"
              data-active="true"
            >
              <div className="section-background" />
              <div
                className="content-wrapper"
                style={{}}
                id="yui_3_17_2_1_1664274854727_74"
              >
                <div className="content" id="yui_3_17_2_1_1664274854727_73">
                  <div
                    className="sqs-layout sqs-grid-12 columns-12"
                    data-type="page-section"
                    id="page-section-61658b0c073f423893f75b29"
                  >
                    <div
                      className="row sqs-row"
                      id="yui_3_17_2_1_1664274854727_72"
                    >
                      <div className="col sqs-col-0 span-0" />
                      <div className="col sqs-col-6 span-6">
                        <div
                          className="sqs-block html-block sqs-block-html"
                          data-block-type={2}
                          id="block-yui_3_17_2_1_1634043034645_104410"
                        >
                          <div className="sqs-block-content">
                            <p
                              className="preFade fadeIn"
                              style={{
                                transitionTimingFunction: "ease",
                                transitionDuration: "0.8s",
                                transitionDelay: "0.0654545s"
                              }}
                            >
                              Our Idea
                            </p>
                          </div>
                        </div>
                        <div
                          className="sqs-block code-block sqs-block-code"
                          data-block-type={23}
                          id="block-yui_3_17_2_1_1634043034645_36780"
                        >
                          <div className="sqs-block-content">
                            <h2
                              className="preSlide slideIn"
                              style={{
                                transitionTimingFunction: "ease",
                                transitionDuration: "0.8s",
                                transitionDelay: "0.0709091s"
                              }}
                            >
                              Innovating the hydrogen economy by reinventing
                              fuel cell{" "}
                              <span style={{ color: "#4684FF" }}>
                                architecture and chemistry.
                              </span>
                              <br />
                            </h2>
                          </div>
                        </div>
                        <div
                          className="sqs-block html-block sqs-block-html"
                          data-block-type={2}
                          id="block-820017e57a366f8eda7a"
                        >
                          <div className="sqs-block-content">
                            <p
                              className="preFade fadeIn"
                              style={{
                                transitionTimingFunction: "ease",
                                transitionDuration: "0.8s",
                                transitionDelay: "0.0763636s"
                              }}
                            >
                              Energy demand is surging and current batteries are
                              not sustainable. With a low lifecycle, most
                              chemistries can not keep up with new technology
                              energy demands. Therefore we want to create a
                              battery solution that can be recycled, has a
                              lifespan of +15 years, and grows with your energy
                              needs.
                            </p>
                          </div>
                        </div>
                      </div>
                      <div
                        className="col sqs-col-6 span-6"
                        id="yui_3_17_2_1_1664274854727_71"
                      >
                        <div
                          className="sqs-block image-block sqs-block-image sqs-text-ready"
                          data-block-type={5}
                          id="block-yui_3_17_2_1_1634043034645_122911"
                        >
                          <div
                            className="sqs-block-content"
                            id="yui_3_17_2_1_1664274854727_70"
                          >
                            <div
                              className="image-block-outer-wrapper layout-caption-below design-layout-inline combination-animation-site-default individual-animation-site-default individual-text-animation-site-default animation-loaded"
                              data-test="image-block-inline-outer-wrapper"
                              id="yui_3_17_2_1_1664274854727_69"
                            >
                              <figure
                                className="sqs-block-image-figure intrinsic"
                                style={{ maxWidth: 1920 }}
                                id="yui_3_17_2_1_1664274854727_68"
                              >
                                <div
                                  className="image-block-wrapper preSlide slideIn"
                                  data-animation-role="image"
                                  id="yui_3_17_2_1_1664274854727_67"
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.0818182s"
                                  }}
                                >
                                  <div
                                    className="sqs-image-shape-container-element has-aspect-ratio"
                                    style={{
                                      position: "relative",
                                      paddingBottom: "56.25%",
                                      overflow: "hidden"
                                    }}
                                    id="yui_3_17_2_1_1664274854727_66"
                                  >
                                    <noscript>
                                      &lt;img
                                      src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/1634046069131-O4VLZSB0AXKBA8GQNJ04/Frame-000+%28199%29.png"
                                      alt="Frame-000 (199).png"&gt;
                                    </noscript>
                                    <img
                                      className="thumb-image loaded"
                                      data-src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/1634046069131-O4VLZSB0AXKBA8GQNJ04/Frame-000+%28199%29.png"
                                      data-image="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/1634046069131-O4VLZSB0AXKBA8GQNJ04/Frame-000+%28199%29.png"
                                      data-image-dimensions="1920x1080"
                                      data-image-focal-point="0.5,0.5"
                                      data-load="false"
                                      data-image-id="61659073c5c508467d696c38"
                                      data-type="image"
                                      style={{
                                        left: "-0.0360282%",
                                        top: "0%",
                                        width: "100.072%",
                                        height: "100%",
                                        position: "absolute"
                                      }}
                                      alt="Frame-000 (199).png"
                                      data-image-resolution="2500w"
                                      src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/1634046069131-O4VLZSB0AXKBA8GQNJ04/Frame-000+%28199%29.png?format=2500w"
                                    />
                                  </div>
                                </div>
                              </figure>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </section>
            <section
              data-test="page-section"
              data-section-theme="black"
              className="page-section layout-engine-section background-width--full-bleed section-height--large content-width--medium horizontal-alignment--center vertical-alignment--middle black"
              data-section-id="6168453eaa142e077862ccc8"
              data-controller="SectionWrapperController"
              data-current-styles='{ "backgroundImage": { "id": "61850d043b117e44249a3fda", "recordType": 2, "addedOn": 1636109572658, "updatedOn": 1636109572684, "workflowState": 1, "publishOn": 1636109572658, "authorId": "617ab393b49a9d769760fc22", "systemDataId": "5044210b-efda-481f-8f66-41afb131c44e", "systemDataVariants": "1600x900,100w,300w,500w,750w,1000w,1500w", "systemDataSourceType": "GIF", "filename": "Comp-1.gif", "mediaFocalPoint": { "x": 0.5, "y": 0.5, "source": 3 }, "colorData": { "topLeftAverage": "000000", "topRightAverage": "000000", "bottomLeftAverage": "000000", "bottomRightAverage": "000000", "centerAverage": "909088", "suggestedBgColor": "000000" }, "urlId": "0mkrw3oo5rxnxvnovv92d046a124gc", "title": "", "body": null, "likeCount": 0, "commentCount": 0, "publicCommentCount": 0, "commentState": 2, "unsaved": false, "author": { "id": "617ab393b49a9d769760fc22", "displayName": "Zacariah Heim", "firstName": "Zacariah", "lastName": "Heim", "bio": "" }, "assetUrl": "https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/5044210b-efda-481f-8f66-41afb131c44e/Comp-1.gif", "contentType": "image/gif", "items": [ ], "pushedServices": { }, "pendingPushedServices": { }, "recordTypeLabel": "image", "originalSize": "1600x900" }, "imageOverlayOpacity": 0.71, "backgroundWidth": "background-width--full-bleed", "sectionHeight": "section-height--large", "customSectionHeight": 85, "horizontalAlignment": "horizontal-alignment--center", "verticalAlignment": "vertical-alignment--middle", "contentWidth": "content-width--medium", "sectionTheme": "black", "sectionAnimation": "none", "backgroundMode": "video", "imageEffect": "tilt" }'
              data-current-context='{ "video": { "playbackSpeed": 1.5, "filter": 1, "filterStrength": 100, "zoom": 0, "videoSourceProvider": "native", "nativeVideoContentItem": { "id": "617a6e61e2b9eb73556be4b2", "recordType": 61, "addedOn": 1635413601938, "updatedOn": 1635413601938, "authorId": "6141c52ef3ca133b0aa7bb6f", "systemDataId": "efc7c6cd-844e-4ba3-a0a0-30bf6f7519e1", "systemDataVariants": "1920:1080,640:360", "systemDataSourceType": "mp4", "filename": "Comp 1.mp4", "body": null, "likeCount": 0, "commentCount": 0, "publicCommentCount": 0, "commentState": 1, "author": { "id": "6141c52ef3ca133b0aa7bb6f", "displayName": "Laura Lang", "firstName": "Laura", "lastName": "Lang", "avatarUrl": "https://static1.squarespace.com/static/images/6141c52ff30eda74acf2a221", "bio": "", "avatarAssetUrl": "https://static1.squarespace.com/static/images/6141c52ff30eda74acf2a221" }, "contentType": "video/mp4", "structuredContent": { "_type": "SqspHostedVideo", "videoCodec": "h264", "audioCodec": "aac", "alexandriaUrl": "https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/efc7c6cd-844e-4ba3-a0a0-30bf6f7519e1/{variant}", "alexandriaLibraryId": "613f323315e7c403d0d6c265", "aspectRatio": 1.7777777777777777, "durationSeconds": 30.058667 }, "videoCodec": "h264", "audioCodec": "aac", "alexandriaUrl": "https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/efc7c6cd-844e-4ba3-a0a0-30bf6f7519e1/{variant}", "alexandriaLibraryId": "613f323315e7c403d0d6c265", "aspectRatio": 1.7777777777777777, "durationSeconds": 30.058667, "items": [ ], "pushedServices": { }, "pendingPushedServices": { }, "recordTypeLabel": "sqsp-hosted-video", "originalSize": "1920:1080" } }, "backgroundImageId": null, "backgroundMediaEffect": null, "typeName": "page" }'
              data-animation="none"
              data-controllers-bound="SectionWrapperController"
              data-active="true"
            >
              <div className="section-background">
                <div
                  data-controller="VideoBackgroundNative"
                  data-controllers-bound="VideoBackgroundNative"
                >
                  <div
                    className="sqs-video-background-native content-fill"
                    data-config-native-video='{ "id": "617a6e61e2b9eb73556be4b2", "recordType": 61, "addedOn": 1635413601938, "updatedOn": 1635413601938, "authorId": "6141c52ef3ca133b0aa7bb6f", "systemDataId": "efc7c6cd-844e-4ba3-a0a0-30bf6f7519e1", "systemDataVariants": "1920:1080,640:360", "systemDataSourceType": "mp4", "filename": "Comp 1.mp4", "body": null, "likeCount": 0, "commentCount": 0, "publicCommentCount": 0, "commentState": 1, "author": { "id": "6141c52ef3ca133b0aa7bb6f", "displayName": "Laura Lang", "firstName": "Laura", "lastName": "Lang", "avatarUrl": "https://static1.squarespace.com/static/images/6141c52ff30eda74acf2a221", "bio": "", "avatarAssetUrl": "https://static1.squarespace.com/static/images/6141c52ff30eda74acf2a221" }, "contentType": "video/mp4", "structuredContent": { "_type": "SqspHostedVideo", "videoCodec": "h264", "audioCodec": "aac", "alexandriaUrl": "https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/efc7c6cd-844e-4ba3-a0a0-30bf6f7519e1/{variant}", "alexandriaLibraryId": "613f323315e7c403d0d6c265", "aspectRatio": 1.7777777777777777, "durationSeconds": 30.058667 }, "videoCodec": "h264", "audioCodec": "aac", "alexandriaUrl": "https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/efc7c6cd-844e-4ba3-a0a0-30bf6f7519e1/{variant}", "alexandriaLibraryId": "613f323315e7c403d0d6c265", "aspectRatio": 1.7777777777777777, "durationSeconds": 30.058667, "items": [ ], "pushedServices": { }, "pendingPushedServices": { }, "recordTypeLabel": "sqsp-hosted-video", "originalSize": "1920:1080" }'
                    data-config-playback-speed="1.5"
                    data-config-filter={1}
                    data-config-filter-strength={100}
                  >
                    <div className="sqs-video-background-native__video-player video-player video-player--medium video-player--large">
                      <div
                        tabIndex={0}
                        className="plyr plyr--full-ui plyr--video plyr--html5 plyr--pip-supported plyr--playing plyr--hide-controls"
                      >
                        <div className="plyr__controls" style={{}} />
                        <div className="plyr__video-wrapper">
                          <video
                            autoPlay
                            loop
                            muted
                            playsInline
                            src="https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/efc7c6cd-844e-4ba3-a0a0-30bf6f7519e1/mp4-h264-aac-1920:1080"
                          >
                            <source src="https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/efc7c6cd-844e-4ba3-a0a0-30bf6f7519e1/mp4-h264-aac-1920:1080" />
                            <source src="https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/efc7c6cd-844e-4ba3-a0a0-30bf6f7519e1/mp4-h264-aac-640:360" />
                          </video>
                          <div className="plyr__poster" />
                        </div>
                        <div className="plyr__captions" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <div className="content-wrapper" style={{}}>
                <div className="content">
                  <div
                    className="sqs-layout sqs-grid-12 columns-12 empty"
                    data-type="page-section"
                    data-updated-on={1664199239723}
                    id="page-section-6168453eaa142e077862ccc8"
                  />
                </div>
              </div>
            </section>
            <section
              data-test="page-section"
              data-section-theme="black-bold"
              className="page-section layout-engine-section background-width--full-bleed section-height--small content-width--wide horizontal-alignment--center vertical-alignment--middle black-bold"
              data-section-id="615191bf0e64f47eb70306a5"
              data-controller="SectionWrapperController"
              data-current-styles='{ "imageOverlayOpacity": 0.15, "backgroundWidth": "background-width--full-bleed", "sectionHeight": "section-height--small", "horizontalAlignment": "horizontal-alignment--center", "verticalAlignment": "vertical-alignment--middle", "contentWidth": "content-width--wide", "sectionTheme": "black-bold", "sectionAnimation": "none", "backgroundMode": "image", "imageEffect": "tilt" }'
              data-current-context='{ "video": { "playbackSpeed": 0.5, "filter": 1, "filterStrength": 0, "zoom": 0, "videoSourceProvider": "none" }, "backgroundImageId": null, "backgroundMediaEffect": null, "typeName": "page" }'
              data-animation="none"
              data-controllers-bound="SectionWrapperController"
              id="yui_3_17_2_1_1664274854727_101"
              data-active="true"
            >
              <div className="section-background" />
              <div
                className="content-wrapper"
                style={{}}
                id="yui_3_17_2_1_1664274854727_100"
              >
                <div className="content" id="yui_3_17_2_1_1664274854727_99">
                  <div
                    className="sqs-layout sqs-grid-12 columns-12"
                    data-type="page-section"
                    id="page-section-615191bf0e64f47eb70306a5"
                  >
                    <div
                      className="row sqs-row"
                      id="yui_3_17_2_1_1664274854727_98"
                    >
                      <div
                        className="col sqs-col-12 span-12"
                        id="yui_3_17_2_1_1664274854727_97"
                      >
                        <div
                          className="row sqs-row"
                          id="yui_3_17_2_1_1664274854727_96"
                        >
                          <div className="col sqs-col-4 span-4">
                            <div
                              className="sqs-block html-block sqs-block-html"
                              data-block-type={2}
                              id="block-yui_3_17_2_1_1632755459522_20489"
                            >
                              <div className="sqs-block-content">
                                <p
                                  className="preFade fadeIn"
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.0872727s"
                                  }}
                                >
                                  Our Solution
                                </p>
                                <h2
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.0927273s"
                                  }}
                                  className="preSlide slideIn"
                                >
                                  Reinventing fuel cell architecture and
                                  chemistry.
                                </h2>
                              </div>
                            </div>
                          </div>
                          <div
                            className="col sqs-col-5 span-5"
                            id="yui_3_17_2_1_1664274854727_95"
                          >
                            <div
                              className="sqs-block image-block sqs-block-image sqs-text-ready"
                              data-block-type={5}
                              id="block-yui_3_17_2_1_1632490907388_49121"
                            >
                              <div
                                className="sqs-block-content"
                                id="yui_3_17_2_1_1664274854727_94"
                              >
                                <div
                                  className="image-block-outer-wrapper layout-caption-hidden design-layout-inline combination-animation-custom individual-animation-slide-down individual-text-animation-site-default animation-loaded"
                                  data-test="image-block-inline-outer-wrapper"
                                  id="yui_3_17_2_1_1664274854727_93"
                                >
                                  <figure
                                    className="sqs-block-image-figure intrinsic"
                                    style={{ maxWidth: 811 }}
                                    id="yui_3_17_2_1_1664274854727_92"
                                  >
                                    <div
                                      className="image-block-wrapper"
                                      data-animation-role="image"
                                      data-animation-override
                                      id="yui_3_17_2_1_1664274854727_91"
                                    >
                                      <div
                                        className="sqs-image-shape-container-element has-aspect-ratio"
                                        style={{
                                          position: "relative",
                                          paddingBottom: "133.04562377929688%",
                                          overflow: "hidden"
                                        }}
                                        id="yui_3_17_2_1_1664274854727_90"
                                      >
                                        <noscript>
                                          &lt;img
                                          src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/1634039201470-BMVCJA72SEN07MPMN7RY/export+SQ.png"
                                          alt="export SQ.png"&gt;
                                        </noscript>
                                        <img
                                          className="thumb-image loaded"
                                          data-src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/1634039201470-BMVCJA72SEN07MPMN7RY/export+SQ.png"
                                          data-image="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/1634039201470-BMVCJA72SEN07MPMN7RY/export+SQ.png"
                                          data-image-dimensions="811x1079"
                                          data-image-focal-point="0.5,0.5"
                                          data-load="false"
                                          data-image-id="616575a15854f17539c2ac48"
                                          data-type="image"
                                          style={{
                                            left: "-0.0294621%",
                                            top: "0%",
                                            width: "100.059%",
                                            height: "100%",
                                            position: "absolute"
                                          }}
                                          alt="export SQ.png"
                                          data-image-resolution="1500w"
                                          src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/1634039201470-BMVCJA72SEN07MPMN7RY/export+SQ.png?format=1500w"
                                        />
                                      </div>
                                    </div>
                                  </figure>
                                </div>
                              </div>
                            </div>
                          </div>
                          <div className="col sqs-col-3 span-3">
                            <div
                              className="sqs-block code-block sqs-block-code"
                              data-block-type={23}
                              id="block-yui_3_17_2_1_1633346127540_37704"
                            >
                              <div className="sqs-block-content">
                                <h4
                                  className="preFade fadeIn"
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.0981818s"
                                  }}
                                >
                                  <span style={{ color: "#4684FF" }}>01.</span>{" "}
                                  fueled with
                                  <br />
                                  hyperfine water mist
                                </h4>
                              </div>
                            </div>
                            <div
                              className="sqs-block html-block sqs-block-html"
                              data-block-type={2}
                              id="block-yui_3_17_2_1_1633346127540_45819"
                            >
                              <div className="sqs-block-content">
                                <p
                                  className="sqsrte-small preFade fadeIn"
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.103636s"
                                  }}
                                >
                                  Clean.&nbsp; Metal free.&nbsp;
                                  Eco-friendly.&nbsp;&nbsp;Water electrolyte.
                                </p>
                              </div>
                            </div>
                            <div
                              className="sqs-block horizontalrule-block sqs-block-horizontalrule"
                              data-block-type={47}
                              id="block-yui_3_17_2_1_1633504683995_29217"
                            >
                              <div className="sqs-block-content">
                                <hr />
                              </div>
                            </div>
                            <div
                              className="sqs-block code-block sqs-block-code"
                              data-block-type={23}
                              id="block-yui_3_17_2_1_1632754960359_31279"
                            >
                              <div className="sqs-block-content">
                                <h4
                                  className="preFade fadeIn"
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.109091s"
                                  }}
                                >
                                  <span style={{ color: "#FBFF32" }}>02.</span>{" "}
                                  safe storage material
                                </h4>
                              </div>
                            </div>
                            <div
                              className="sqs-block html-block sqs-block-html"
                              data-block-type={2}
                              id="block-yui_3_17_2_1_1632754960359_34811"
                            >
                              <div className="sqs-block-content">
                                <p
                                  className="sqsrte-small preFade fadeIn"
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.114545s"
                                  }}
                                >
                                  ETVR hydrogen-based energy storage is
                                  non-gaseous, therefore completely safe
                                </p>
                              </div>
                            </div>
                            <div
                              className="sqs-block horizontalrule-block sqs-block-horizontalrule"
                              data-block-type={47}
                              id="block-yui_3_17_2_1_1633504683995_44842"
                            >
                              <div className="sqs-block-content">
                                <hr />
                              </div>
                            </div>
                            <div
                              className="sqs-block code-block sqs-block-code"
                              data-block-type={23}
                              id="block-yui_3_17_2_1_1632754960359_38550"
                            >
                              <div className="sqs-block-content">
                                <h4
                                  style={{
                                    color: "rgb(255, 255, 255)",
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.12s"
                                  }}
                                  className="preFade fadeIn"
                                >
                                  03. environmentally friendly catalysts
                                </h4>
                              </div>
                            </div>
                            <div
                              className="sqs-block html-block sqs-block-html"
                              data-block-type={2}
                              id="block-yui_3_17_2_1_1632754960359_40053"
                            >
                              <div className="sqs-block-content">
                                <p
                                  className="sqsrte-small preFade fadeIn"
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.125455s"
                                  }}
                                >
                                  Non-toxic. Non-platinum group metals. 80%
                                  recyclable and 100% possible.
                                </p>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </section>
            <section
              data-test="page-section"
              data-section-theme="black-bold"
              className="page-section layout-engine-section background-width--full-bleed section-height--large content-width--narrow horizontal-alignment--center vertical-alignment--middle black-bold"
              data-section-id="615d9158e6e7b1308e987468"
              data-controller="SectionWrapperController"
              data-current-styles='{ "backgroundImage": { "id": "61850a559ee172551ed98a3c", "recordType": 2, "addedOn": 1636108885542, "updatedOn": 1636108885573, "workflowState": 1, "publishOn": 1636108885542, "authorId": "617ab393b49a9d769760fc22", "systemDataId": "a9f9eb01-5706-4b1d-9158-beae665df700", "systemDataVariants": "1920x1080,100w,300w,500w,750w,1000w,1500w", "systemDataSourceType": "GIF", "filename": "ETVR_Mist.gif", "mediaFocalPoint": { "x": 0.5, "y": 0.5, "source": 3 }, "colorData": { "topLeftAverage": "000000", "topRightAverage": "000000", "bottomLeftAverage": "000000", "bottomRightAverage": "000000", "centerAverage": "4d4d55", "suggestedBgColor": "000000" }, "urlId": "5gzw4buro643vmra88olhohsgffwm8", "title": "", "body": null, "likeCount": 0, "commentCount": 0, "publicCommentCount": 0, "commentState": 2, "unsaved": false, "author": { "id": "617ab393b49a9d769760fc22", "displayName": "Zacariah Heim", "firstName": "Zacariah", "lastName": "Heim", "bio": "" }, "assetUrl": "https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/a9f9eb01-5706-4b1d-9158-beae665df700/ETVR_Mist.gif", "contentType": "image/gif", "items": [ ], "pushedServices": { }, "pendingPushedServices": { }, "recordTypeLabel": "image", "originalSize": "1920x1080" }, "imageOverlayOpacity": 0.19, "backgroundWidth": "background-width--full-bleed", "sectionHeight": "section-height--large", "customSectionHeight": 85, "horizontalAlignment": "horizontal-alignment--center", "verticalAlignment": "vertical-alignment--middle", "contentWidth": "content-width--narrow", "sectionTheme": "black-bold", "sectionAnimation": "none", "backgroundMode": "video", "imageEffect": "none" }'
              data-current-context='{ "video": { "playbackSpeed": 0.5, "filter": 1, "filterStrength": 0, "zoom": 0, "videoSourceProvider": "native", "nativeVideoContentItem": { "id": "616571b0b534bb7a74df2fba", "recordType": 61, "addedOn": 1634038192954, "updatedOn": 1634038192954, "authorId": "6141c52ef3ca133b0aa7bb6f", "systemDataId": "d94cc48a-cf21-4c29-a32c-fd42e5bb800b", "systemDataVariants": "1920:1080,640:360", "systemDataSourceType": "mp4", "filename": "ETVR mist.mp4", "body": null, "likeCount": 0, "commentCount": 0, "publicCommentCount": 0, "commentState": 1, "author": { "id": "6141c52ef3ca133b0aa7bb6f", "displayName": "Laura Lang", "firstName": "Laura", "lastName": "Lang", "avatarUrl": "https://static1.squarespace.com/static/images/6141c52ff30eda74acf2a221", "bio": "", "avatarAssetUrl": "https://static1.squarespace.com/static/images/6141c52ff30eda74acf2a221" }, "contentType": "video/mp4", "structuredContent": { "_type": "SqspHostedVideo", "videoCodec": "h264", "alexandriaUrl": "https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/d94cc48a-cf21-4c29-a32c-fd42e5bb800b/{variant}", "alexandriaLibraryId": "613f323315e7c403d0d6c265", "aspectRatio": 1.7777777777777777, "durationSeconds": 7.540867 }, "videoCodec": "h264", "alexandriaUrl": "https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/d94cc48a-cf21-4c29-a32c-fd42e5bb800b/{variant}", "alexandriaLibraryId": "613f323315e7c403d0d6c265", "aspectRatio": 1.7777777777777777, "durationSeconds": 7.540867, "items": [ ], "pushedServices": { }, "pendingPushedServices": { }, "recordTypeLabel": "sqsp-hosted-video", "originalSize": "1920:1080" } }, "backgroundImageId": null, "backgroundMediaEffect": null, "typeName": "page" }'
              data-animation="none"
              data-controllers-bound="SectionWrapperController"
              data-active="true"
            >
              <div className="section-background">
                <div
                  data-controller="VideoBackgroundNative"
                  data-controllers-bound="VideoBackgroundNative"
                >
                  <div
                    className="sqs-video-background-native content-fill"
                    data-config-native-video='{ "id": "616571b0b534bb7a74df2fba", "recordType": 61, "addedOn": 1634038192954, "updatedOn": 1634038192954, "authorId": "6141c52ef3ca133b0aa7bb6f", "systemDataId": "d94cc48a-cf21-4c29-a32c-fd42e5bb800b", "systemDataVariants": "1920:1080,640:360", "systemDataSourceType": "mp4", "filename": "ETVR mist.mp4", "body": null, "likeCount": 0, "commentCount": 0, "publicCommentCount": 0, "commentState": 1, "author": { "id": "6141c52ef3ca133b0aa7bb6f", "displayName": "Laura Lang", "firstName": "Laura", "lastName": "Lang", "avatarUrl": "https://static1.squarespace.com/static/images/6141c52ff30eda74acf2a221", "bio": "", "avatarAssetUrl": "https://static1.squarespace.com/static/images/6141c52ff30eda74acf2a221" }, "contentType": "video/mp4", "structuredContent": { "_type": "SqspHostedVideo", "videoCodec": "h264", "alexandriaUrl": "https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/d94cc48a-cf21-4c29-a32c-fd42e5bb800b/{variant}", "alexandriaLibraryId": "613f323315e7c403d0d6c265", "aspectRatio": 1.7777777777777777, "durationSeconds": 7.540867 }, "videoCodec": "h264", "alexandriaUrl": "https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/d94cc48a-cf21-4c29-a32c-fd42e5bb800b/{variant}", "alexandriaLibraryId": "613f323315e7c403d0d6c265", "aspectRatio": 1.7777777777777777, "durationSeconds": 7.540867, "items": [ ], "pushedServices": { }, "pendingPushedServices": { }, "recordTypeLabel": "sqsp-hosted-video", "originalSize": "1920:1080" }'
                    data-config-playback-speed="0.5"
                    data-config-filter={1}
                    data-config-filter-strength={0}
                  >
                    <div className="sqs-video-background-native__video-player video-player video-player--medium video-player--large">
                      <div
                        tabIndex={0}
                        className="plyr plyr--full-ui plyr--video plyr--html5 plyr--pip-supported plyr--playing plyr--hide-controls"
                      >
                        <div className="plyr__controls" style={{}} />
                        <div className="plyr__video-wrapper">
                          <video
                            autoPlay
                            loop
                            muted
                            playsInline
                            src="https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/d94cc48a-cf21-4c29-a32c-fd42e5bb800b/mp4-h264-1920:1080"
                          >
                            <source
                              src="https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/d94cc48a-cf21-4c29-a32c-fd42e5bb800b/mp4-h264-1920:1080"
                              type={"video/mp4"}
                            />
                            <source
                              src="https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/d94cc48a-cf21-4c29-a32c-fd42e5bb800b/mp4-h264-640:360"
                              type={"video/mp4"}
                            />
                          </video>
                          <div className="plyr__poster" />
                        </div>
                        <div className="plyr__captions" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <div className="content-wrapper" style={{}}>
                <div className="content">
                  <div
                    className="sqs-layout sqs-grid-12 columns-12"
                    data-type="page-section"
                    id="page-section-615d9158e6e7b1308e987468"
                  >
                    <div className="row sqs-row">
                      <div className="col sqs-col-12 span-12">
                        <div
                          className="sqs-block html-block sqs-block-html"
                          data-block-type={2}
                          id="block-yui_3_17_2_1_1634115085045_18409"
                        >
                          <div className="sqs-block-content">
                            <p
                              className="preFade fadeIn"
                              style={{
                                transitionTimingFunction: "ease",
                                transitionDuration: "0.8s",
                                transitionDelay: "0.130909s"
                              }}
                            >
                              Bringing space technologies down to earth
                            </p>
                            <p
                              className="preFade fadeIn"
                              style={{
                                transitionTimingFunction: "ease",
                                transitionDuration: "0.8s",
                                transitionDelay: "0.136364s"
                              }}
                            >
                              <br />
                            </p>
                          </div>
                        </div>
                        <div
                          className="sqs-block code-block sqs-block-code"
                          data-block-type={23}
                          id="block-yui_3_17_2_1_1633504683995_186348"
                        >
                          <div className="sqs-block-content">
                            <h2
                              className="preSlide slideIn"
                              style={{
                                transitionTimingFunction: "ease",
                                transitionDuration: "0.8s",
                                transitionDelay: "0.141818s"
                              }}
                            >
                              “[...]{" "}
                              <span style={{ color: "#FAFF00" }}>
                                nickel-hydrogen batteries have become the
                                primary energy storage system
                              </span>{" "}
                              used for geosynchronous- orbit communication
                              satellites."
                            </h2>
                          </div>
                        </div>
                        <div
                          className="sqs-block html-block sqs-block-html"
                          data-block-type={2}
                          id="block-9aee549960d69123f272"
                        >
                          <div className="sqs-block-content">
                            <p
                              className="sqsrte-small preFade fadeIn"
                              style={{
                                transitionTimingFunction: "ease",
                                transitionDuration: "0.8s",
                                transitionDelay: "0.147273s"
                              }}
                            >
                              NASA Handbook for Nickel-Hydrogen Batteries
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </section>
            <section
              data-test="page-section"
              data-section-theme="black-bold"
              className="page-section layout-engine-section background-width--full-bleed content-width--wide horizontal-alignment--center vertical-alignment--middle black-bold"
              data-section-id="61408c33990742119e26d43a"
              data-controller="SectionWrapperController"
              data-current-styles='{ "imageOverlayOpacity": 0.15, "backgroundWidth": "background-width--full-bleed", "sectionHeight": "section-height--custom", "customSectionHeight": 60, "horizontalAlignment": "horizontal-alignment--center", "verticalAlignment": "vertical-alignment--middle", "contentWidth": "content-width--wide", "customContentWidth": 60, "sectionTheme": "black-bold", "sectionAnimation": "none", "backgroundMode": "image" }'
              data-current-context='{ "video": { "playbackSpeed": 0.5, "filter": 1, "filterStrength": 0, "zoom": 0, "videoSourceProvider": "none" }, "backgroundImageId": null, "backgroundMediaEffect": null, "typeName": "page" }'
              data-animation="none"
              style={{ minHeight: "60vh" }}
              data-controllers-bound="SectionWrapperController"
              id="yui_3_17_2_1_1664274854727_126"
              data-active="true"
            >
              <div className="section-background" />
              <div
                className="content-wrapper"
                style={{
                  paddingTop: "calc(60vmax / 10)",
                  paddingBottom: "calc(60vmax / 10)"
                }}
                id="yui_3_17_2_1_1664274854727_125"
              >
                <div className="content" id="yui_3_17_2_1_1664274854727_124">
                  <div
                    className="sqs-layout sqs-grid-12 columns-12"
                    data-type="page-section"
                    id="page-section-61408c33990742119e26d43a"
                  >
                    <div
                      className="row sqs-row"
                      id="yui_3_17_2_1_1664274854727_123"
                    >
                      <div
                        className="col sqs-col-12 span-12"
                        id="yui_3_17_2_1_1664274854727_122"
                      >
                        <div
                          className="row sqs-row"
                          id="yui_3_17_2_1_1664274854727_121"
                        >
                          <div className="col sqs-col-5 span-5">
                            <div className="row sqs-row">
                              <div className="col sqs-col-4 span-4">
                                <div
                                  className="sqs-block html-block sqs-block-html"
                                  data-block-type={2}
                                  id="block-yui_3_17_2_1_1632737681202_7898"
                                >
                                  <div className="sqs-block-content">
                                    <p
                                      className="preFade fadeIn"
                                      style={{
                                        transitionTimingFunction: "ease",
                                        transitionDuration: "0.8s",
                                        transitionDelay: "0.152727s"
                                      }}
                                    >
                                      Performance
                                    </p>
                                    <h2
                                      style={{
                                        transitionTimingFunction: "ease",
                                        transitionDuration: "0.8s",
                                        transitionDelay: "0.158182s"
                                      }}
                                      className="preSlide slideIn"
                                    >
                                      Comparing ETVR to a common Lithium-Ion
                                      battery.
                                    </h2>
                                  </div>
                                </div>
                              </div>
                              <div className="col sqs-col-1 span-1">
                                <div
                                  className="sqs-block spacer-block sqs-block-spacer sized vsize-1"
                                  data-block-type={21}
                                  id="block-yui_3_17_2_1_1632755967850_18853"
                                >
                                  <div className="sqs-block-content">
                                    &nbsp;
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                          <div
                            className="col sqs-col-7 span-7"
                            id="yui_3_17_2_1_1664274854727_120"
                          >
                            <div
                              className="sqs-block image-block sqs-block-image sqs-text-ready"
                              data-block-type={5}
                              id="block-yui_3_17_2_1_1631619351902_24411"
                            >
                              <div
                                className="sqs-block-content"
                                id="yui_3_17_2_1_1664274854727_119"
                              >
                                <div
                                  className="image-block-outer-wrapper layout-caption-hidden design-layout-inline combination-animation-site-default individual-animation-site-default individual-text-animation-site-default animation-loaded"
                                  data-test="image-block-inline-outer-wrapper"
                                  id="yui_3_17_2_1_1664274854727_118"
                                >
                                  <figure
                                    className="sqs-block-image-figure intrinsic"
                                    style={{ maxWidth: 1316 }}
                                    id="yui_3_17_2_1_1664274854727_117"
                                  >
                                    <div
                                      className="image-block-wrapper preSlide slideIn"
                                      data-animation-role="image"
                                      id="yui_3_17_2_1_1664274854727_116"
                                      style={{
                                        transitionTimingFunction: "ease",
                                        transitionDuration: "0.8s",
                                        transitionDelay: "0.163636s"
                                      }}
                                    >
                                      <div
                                        className="sqs-image-shape-container-element has-aspect-ratio"
                                        style={{
                                          position: "relative",
                                          paddingBottom: "66.10942840576172%",
                                          overflow: "hidden"
                                        }}
                                        id="yui_3_17_2_1_1664274854727_115"
                                      >
                                        <noscript>
                                          &lt;img
                                          src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/1634042204423-XF6168S7CQ8FIF6T6A5Q/Frame+1.png"
                                          alt="Frame 1.png"&gt;
                                        </noscript>
                                        <img
                                          className="thumb-image loaded"
                                          data-src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/1634042204423-XF6168S7CQ8FIF6T6A5Q/Frame+1.png"
                                          data-image="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/1634042204423-XF6168S7CQ8FIF6T6A5Q/Frame+1.png"
                                          data-image-dimensions="1316x870"
                                          data-image-focal-point="0.5,0.5"
                                          data-load="false"
                                          data-image-id="6165815c75f89d75cc102ee2"
                                          data-type="image"
                                          style={{
                                            left: "-0.00405978%",
                                            top: "0%",
                                            width: "100.008%",
                                            height: "100%",
                                            position: "absolute"
                                          }}
                                          alt="Frame 1.png"
                                          data-image-resolution="2500w"
                                          src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/1634042204423-XF6168S7CQ8FIF6T6A5Q/Frame+1.png?format=2500w"
                                        />
                                      </div>
                                    </div>
                                  </figure>
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </section>
            <section
              data-test="page-section"
              data-section-theme="white"
              className="page-section layout-engine-section background-width--full-bleed section-height--small content-width--wide horizontal-alignment--center vertical-alignment--top white"
              data-section-id="613f53e722c62f660b67d0c8"
              data-controller="SectionWrapperController"
              data-current-styles='{ "imageOverlayOpacity": 0.15, "backgroundWidth": "background-width--full-bleed", "sectionHeight": "section-height--small", "horizontalAlignment": "horizontal-alignment--center", "verticalAlignment": "vertical-alignment--top", "contentWidth": "content-width--wide", "sectionTheme": "white", "sectionAnimation": "none", "backgroundMode": "image" }'
              data-current-context='{ "video": { "playbackSpeed": 0.5, "filter": 1, "filterStrength": 0, "zoom": 0, "videoSourceProvider": "none" }, "backgroundImageId": null, "backgroundMediaEffect": null, "typeName": "page" }'
              data-animation="none"
              data-controllers-bound="SectionWrapperController"
              data-active="true"
            >
              <div className="section-background" />
              <div className="content-wrapper" style={{}}>
                <div className="content">
                  <div
                    className="sqs-layout sqs-grid-12 columns-12"
                    data-type="page-section"
                    id="page-section-613f53e722c62f660b67d0c8"
                  >
                    <div className="row sqs-row">
                      <div className="col sqs-col-12 span-12">
                        <div className="row sqs-row">
                          <div className="col sqs-col-4 span-4">
                            <div
                              className="sqs-block html-block sqs-block-html"
                              data-block-type={2}
                              id="block-yui_3_17_2_1_1633072461536_11742"
                            >
                              <div className="sqs-block-content">
                                <p
                                  className="preFade fadeIn"
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.169091s"
                                  }}
                                >
                                  Benefits
                                </p>
                              </div>
                            </div>
                            <div
                              className="sqs-block html-block sqs-block-html"
                              data-block-type={2}
                              id="block-1e3df5737e8704396617"
                            >
                              <div className="sqs-block-content">
                                <h2
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.174545s"
                                  }}
                                  className="preSlide slideIn"
                                >
                                  Innovative features providing the opportunity
                                  to succeed in several markets.
                                </h2>
                              </div>
                            </div>
                          </div>
                          <div className="col sqs-col-1 span-1">
                            <div
                              className="sqs-block spacer-block sqs-block-spacer sized vsize-1"
                              data-block-type={21}
                              id="block-5b30893471c6e3a772ac"
                            >
                              <div className="sqs-block-content">&nbsp;</div>
                            </div>
                          </div>
                          <div className="col sqs-col-3 span-3">
                            <div
                              className="sqs-block html-block sqs-block-html"
                              data-block-type={2}
                              id="block-65f26430839ff06c7aa9"
                            >
                              <div className="sqs-block-content">
                                <h4
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.18s"
                                  }}
                                  className="preFade fadeIn"
                                >
                                  Adaptable to user needs
                                </h4>
                                <p
                                  className="sqsrte-small preFade fadeIn"
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.185455s"
                                  }}
                                >
                                  The HMS system built into every stack uses a
                                  state of the art Battery Managment system.
                                  Keeping track of the system usage profile and
                                  adapting the charge and discharge states to
                                  maintain the ideal efficiency.
                                  <br />
                                </p>
                              </div>
                            </div>
                            <div
                              className="sqs-block spacer-block sqs-block-spacer sized vsize-1"
                              data-block-type={21}
                              id="block-yui_3_17_2_1_1631621690953_33290"
                            >
                              <div className="sqs-block-content">&nbsp;</div>
                            </div>
                            <div
                              className="sqs-block html-block sqs-block-html"
                              data-block-type={2}
                              id="block-2c14cbd8b5f0e845519a"
                            >
                              <div className="sqs-block-content">
                                <h4
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.190909s"
                                  }}
                                  className="preFade fadeIn"
                                >
                                  Non toxic, fire retardant
                                </h4>
                                <p
                                  className="sqsrte-small preFade fadeIn"
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.196364s"
                                  }}
                                >
                                  No toxic chemicals, harmful metals, or
                                  flammable materials are used in manufacturing
                                  or recycling of our H-Bat system. We strive to
                                  maintain and develope a circular life-cycle
                                  for our products.
                                </p>
                              </div>
                            </div>
                          </div>
                          <div className="col sqs-col-1 span-1">
                            <div
                              className="sqs-block spacer-block sqs-block-spacer sized vsize-1"
                              data-block-type={21}
                              id="block-2ba5dbf87e113556b9cb"
                            >
                              <div className="sqs-block-content">&nbsp;</div>
                            </div>
                          </div>
                          <div className="col sqs-col-3 span-3">
                            <div
                              className="sqs-block html-block sqs-block-html"
                              data-block-type={2}
                              id="block-1042f4a76fa0dc35c1f6"
                            >
                              <div className="sqs-block-content">
                                <h4
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.201818s"
                                  }}
                                  className="preFade fadeIn"
                                >
                                  Modular architecture
                                </h4>
                                <p
                                  className="sqsrte-small preFade fadeIn"
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.207273s"
                                  }}
                                >
                                  Our H-Bat system is constructed using a
                                  modular approach. Designed to increase voltage
                                  or amperage per the clients needs. Allowing
                                  our company to load-match the energy storage
                                  system to your load profile.
                                </p>
                              </div>
                            </div>
                            <div
                              className="sqs-block spacer-block sqs-block-spacer sized vsize-1"
                              data-block-type={21}
                              id="block-f393730bf15138af51eb"
                            >
                              <div className="sqs-block-content">&nbsp;</div>
                            </div>
                            <div
                              className="sqs-block html-block sqs-block-html"
                              data-block-type={2}
                              id="block-9f9194db82cd47fc4a81"
                            >
                              <div className="sqs-block-content">
                                <h4
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.212727s"
                                  }}
                                  className="preFade fadeIn"
                                >
                                  Sustainable
                                </h4>
                                <p
                                  className="sqsrte-small preFade fadeIn"
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.218182s"
                                  }}
                                >
                                  The materials within our battery do not
                                  degrade from electrochemical usage, no cell
                                  memory or dendrite growth. What does this
                                  mean? Our system will last a long time,
                                  without cell fatigue.
                                  <br />
                                  <br />
                                  However, due to the nature of how H-Bat stores
                                  hydrogen, the cells capacity decreases
                                  over-time. This is due to an accumulation of
                                  Deuterium inside of the Hydrogen Storage
                                  material.
                                  <br />
                                  <br />
                                  While the user can not replenish the cells, we
                                  can! If a cell fails, or the system begins
                                  lose performance, simply let us know. We can
                                  discharge the accumulated deuterium and have
                                  your cells as good as new. Cell cleaning will
                                  need to be done once every 15 - 20 years.
                                </p>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </section>
            <section
              data-test="page-section"
              data-section-theme="black-bold"
              className="page-section layout-engine-section background-width--full-bleed section-height--medium content-width--medium horizontal-alignment--center vertical-alignment--middle black-bold"
              data-section-id="619c0aea09561253a65e217f"
              data-controller="SectionWrapperController"
              data-current-styles='{ "imageOverlayOpacity": 0.15, "backgroundWidth": "background-width--full-bleed", "sectionHeight": "section-height--medium", "horizontalAlignment": "horizontal-alignment--center", "verticalAlignment": "vertical-alignment--middle", "contentWidth": "content-width--medium", "sectionTheme": "black-bold", "sectionAnimation": "none", "backgroundMode": "image" }'
              data-current-context='{ "video": { "playbackSpeed": 0.5, "filter": 1, "filterStrength": 0, "zoom": 0, "videoSourceProvider": "none" }, "backgroundImageId": null, "backgroundMediaEffect": null, "typeName": "page" }'
              data-animation="none"
              data-controllers-bound="SectionWrapperController"
              id="yui_3_17_2_1_1664274854727_151"
              data-active="true"
            >
              <div className="section-background" />
              <div
                className="content-wrapper"
                style={{}}
                id="yui_3_17_2_1_1664274854727_150"
              >
                <div className="content" id="yui_3_17_2_1_1664274854727_149">
                  <div
                    className="sqs-layout sqs-grid-12 columns-12"
                    data-type="page-section"
                    id="page-section-619c0aea09561253a65e217f"
                  >
                    <div
                      className="row sqs-row"
                      id="yui_3_17_2_1_1664274854727_148"
                    >
                      <div
                        className="col sqs-col-12 span-12"
                        id="yui_3_17_2_1_1664274854727_147"
                      >
                        <div
                          className="sqs-block html-block sqs-block-html"
                          data-block-type={2}
                          id="block-06269746739a3b340655"
                        >
                          <div className="sqs-block-content">
                            <h2
                              style={{
                                textAlign: "center",
                                transitionTimingFunction: "ease",
                                transitionDuration: "0.8s",
                                transitionDelay: "0.223636s"
                              }}
                              className="preSlide slideIn"
                            >
                              Support
                            </h2>
                            <p
                              style={{
                                textAlign: "center",
                                transitionTimingFunction: "ease",
                                transitionDuration: "0.8s",
                                transitionDelay: "0.229091s"
                              }}
                              className="preFade fadeIn"
                            >
                              Advisors and Collaborations
                            </p>
                          </div>
                        </div>
                        <div
                          className="row sqs-row"
                          id="yui_3_17_2_1_1664274854727_146"
                        >
                          <div
                            className="col sqs-col-4 span-4"
                            id="yui_3_17_2_1_1664274854727_145"
                          >
                            <div
                              className="sqs-block image-block sqs-block-image sqs-text-ready"
                              data-block-type={5}
                              id="block-a8d0f93f7d4689dab0f5"
                            >
                              <div
                                className="sqs-block-content"
                                id="yui_3_17_2_1_1664274854727_144"
                              >
                                <div
                                  className="image-block-outer-wrapper layout-caption-below design-layout-inline combination-animation-none individual-animation-none individual-text-animation-none sqs-narrow-width"
                                  data-test="image-block-inline-outer-wrapper"
                                  id="yui_3_17_2_1_1664274854727_143"
                                >
                                  <figure
                                    className="sqs-block-image-figure intrinsic"
                                    style={{ maxWidth: 175 }}
                                    id="yui_3_17_2_1_1664274854727_142"
                                  >
                                    <div
                                      className="image-block-wrapper preSlide slideIn"
                                      data-animation-role="image"
                                      id="yui_3_17_2_1_1664274854727_141"
                                      style={{
                                        transitionTimingFunction: "ease",
                                        transitionDuration: "0.8s",
                                        transitionDelay: "0.234545s"
                                      }}
                                    >
                                      <div
                                        className="sqs-image-shape-container-element has-aspect-ratio"
                                        style={{
                                          position: "relative",
                                          paddingBottom: "102.85714721679688%",
                                          overflow: "hidden"
                                        }}
                                        id="yui_3_17_2_1_1664274854727_140"
                                      >
                                        <noscript>
                                          &lt;img
                                          src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/1b8053eb-cc32-41a4-9849-381c83f8a4bb/OIP.jfif"
                                          alt="OIP"&gt;
                                        </noscript>
                                        <img
                                          className="thumb-image loaded"
                                          data-src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/1b8053eb-cc32-41a4-9849-381c83f8a4bb/OIP.jfif"
                                          data-image="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/1b8053eb-cc32-41a4-9849-381c83f8a4bb/OIP.jfif"
                                          data-image-dimensions="175x180"
                                          data-image-focal-point="0.5,0.5"
                                          alt="OIP"
                                          data-load="false"
                                          data-image-id="619c0c5146c7427e032e7a1c"
                                          data-type="image"
                                          style={{
                                            left: "0%",
                                            top: "0%",
                                            width: "100%",
                                            height: "100%",
                                            position: "absolute"
                                          }}
                                          data-image-resolution="500w"
                                          src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/1b8053eb-cc32-41a4-9849-381c83f8a4bb/OIP.jfif?format=500w"
                                        />
                                      </div>
                                    </div>
                                    <figcaption className="image-caption-wrapper">
                                      <div className="image-caption">
                                        <p
                                          style={{
                                            textAlign: "center",
                                            transitionTimingFunction: "ease",
                                            transitionDuration: "0.8s",
                                            transitionDelay: "0.24s"
                                          }}
                                          className="preFade fadeIn"
                                        >
                                          Have It Made
                                        </p>
                                      </div>
                                    </figcaption>
                                  </figure>
                                </div>
                              </div>
                            </div>
                          </div>
                          <div
                            className="col sqs-col-4 span-4"
                            id="yui_3_17_2_1_1664274854727_170"
                          >
                            <div
                              className="sqs-block image-block sqs-block-image sqs-text-ready"
                              data-block-type={5}
                              id="block-yui_3_17_2_1_1637614241427_53695"
                            >
                              <div
                                className="sqs-block-content"
                                id="yui_3_17_2_1_1664274854727_169"
                              >
                                <div
                                  className="image-block-outer-wrapper layout-caption-below design-layout-inline combination-animation-site-default individual-animation-site-default individual-text-animation-site-default sqs-narrow-width animation-loaded"
                                  data-test="image-block-inline-outer-wrapper"
                                  id="yui_3_17_2_1_1664274854727_168"
                                >
                                  <figure
                                    className="sqs-block-image-figure intrinsic"
                                    style={{ maxWidth: 200 }}
                                    id="yui_3_17_2_1_1664274854727_167"
                                  >
                                    <div
                                      className="image-block-wrapper preSlide slideIn"
                                      data-animation-role="image"
                                      id="yui_3_17_2_1_1664274854727_166"
                                      style={{
                                        transitionTimingFunction: "ease",
                                        transitionDuration: "0.8s",
                                        transitionDelay: "0.245455s"
                                      }}
                                    >
                                      <div
                                        className="sqs-image-shape-container-element has-aspect-ratio"
                                        style={{
                                          position: "relative",
                                          paddingBottom: "100%",
                                          overflow: "hidden"
                                        }}
                                        id="yui_3_17_2_1_1664274854727_165"
                                      >
                                        <noscript>
                                          &lt;img
                                          src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/cf2564d4-87f0-4445-9817-68df85ab5133/1582794156042.jfif"
                                          alt="1582794156042"&gt;
                                        </noscript>
                                        <img
                                          className="thumb-image loaded"
                                          data-src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/cf2564d4-87f0-4445-9817-68df85ab5133/1582794156042.jfif"
                                          data-image="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/cf2564d4-87f0-4445-9817-68df85ab5133/1582794156042.jfif"
                                          data-image-dimensions="200x200"
                                          data-image-focal-point="0.5,0.5"
                                          data-load="false"
                                          data-image-id="619c0d9983835c2453e27ffb"
                                          data-type="image"
                                          style={{
                                            left: "0%",
                                            top: "0%",
                                            width: "100%",
                                            height: "100%",
                                            position: "absolute"
                                          }}
                                          data-image-resolution="500w"
                                          src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/cf2564d4-87f0-4445-9817-68df85ab5133/1582794156042.jfif?format=500w"
                                        />
                                      </div>
                                    </div>
                                  </figure>
                                </div>
                              </div>
                            </div>
                          </div>
                          <div
                            className="col sqs-col-4 span-4"
                            id="yui_3_17_2_1_1664274854727_189"
                          >
                            <div
                              className="sqs-block image-block sqs-block-image sqs-text-ready"
                              data-block-type={5}
                              id="block-020b0f95690e6ec36314"
                            >
                              <div
                                className="sqs-block-content"
                                id="yui_3_17_2_1_1664274854727_188"
                              >
                                <div
                                  className="image-block-outer-wrapper layout-caption-below design-layout-inline combination-animation-none individual-animation-none individual-text-animation-none sqs-narrow-width"
                                  data-test="image-block-inline-outer-wrapper"
                                  id="yui_3_17_2_1_1664274854727_187"
                                >
                                  <figure
                                    className="sqs-block-image-figure intrinsic"
                                    style={{ maxWidth: 3543 }}
                                    id="yui_3_17_2_1_1664274854727_186"
                                  >
                                    <div
                                      className="image-block-wrapper preSlide slideIn"
                                      data-animation-role="image"
                                      id="yui_3_17_2_1_1664274854727_185"
                                      style={{
                                        transitionTimingFunction: "ease",
                                        transitionDuration: "0.8s",
                                        transitionDelay: "0.250909s"
                                      }}
                                    >
                                      <div
                                        className="sqs-image-shape-container-element has-aspect-ratio"
                                        style={{
                                          position: "relative",
                                          paddingBottom: "80.01693725585938%",
                                          overflow: "hidden"
                                        }}
                                        id="yui_3_17_2_1_1664274854727_184"
                                      >
                                        <noscript>
                                          &lt;img
                                          src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/ee19c53c-32b0-42da-98fc-561a246a94f7/UGent_EN-white.png"
                                          alt="UGent_EN-white"&gt;
                                        </noscript>
                                        <img
                                          className="thumb-image loaded"
                                          data-src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/ee19c53c-32b0-42da-98fc-561a246a94f7/UGent_EN-white.png"
                                          data-image="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/ee19c53c-32b0-42da-98fc-561a246a94f7/UGent_EN-white.png"
                                          data-image-dimensions="3543x2835"
                                          data-image-focal-point="0.5,0.5"
                                          alt="UGent_EN-white"
                                          data-load="false"
                                          data-image-id="619c0cebb646ab50493e0a7f"
                                          data-type="image"
                                          style={{
                                            left: "0%",
                                            top: "-0.111616%",
                                            width: "100%",
                                            height: "100.223%",
                                            position: "absolute"
                                          }}
                                          data-image-resolution="750w"
                                          src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/ee19c53c-32b0-42da-98fc-561a246a94f7/UGent_EN-white.png?format=750w"
                                        />
                                      </div>
                                    </div>
                                  </figure>
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                        <div
                          className="sqs-block image-block sqs-block-image sqs-text-ready"
                          data-block-type={5}
                          id="block-1ed3ad8721ca2e5a3f72"
                        >
                          <div
                            className="sqs-block-content"
                            id="yui_3_17_2_1_1664274854727_207"
                          >
                            <div
                              className="image-block-outer-wrapper layout-caption-below design-layout-inline combination-animation-none individual-animation-none individual-text-animation-none"
                              data-test="image-block-inline-outer-wrapper"
                              id="yui_3_17_2_1_1664274854727_206"
                            >
                              <figure
                                className="sqs-block-image-figure intrinsic"
                                style={{ maxWidth: 450 }}
                                id="yui_3_17_2_1_1664274854727_205"
                              >
                                <div
                                  className="image-block-wrapper preSlide slideIn"
                                  data-animation-role="image"
                                  id="yui_3_17_2_1_1664274854727_204"
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.256364s"
                                  }}
                                >
                                  <div
                                    className="sqs-image-shape-container-element has-aspect-ratio"
                                    style={{
                                      position: "relative",
                                      paddingBottom: "23.77777862548828%",
                                      overflow: "hidden"
                                    }}
                                    id="yui_3_17_2_1_1664274854727_203"
                                  >
                                    <noscript>
                                      &lt;img
                                      src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/470b10e2-fada-491c-8d98-905f9440be81/voxdale_logo-1.png"
                                      alt="voxdale_logo-1"&gt;
                                    </noscript>
                                    <img
                                      className="thumb-image loaded"
                                      data-src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/470b10e2-fada-491c-8d98-905f9440be81/voxdale_logo-1.png"
                                      data-image="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/470b10e2-fada-491c-8d98-905f9440be81/voxdale_logo-1.png"
                                      data-image-dimensions="450x107"
                                      data-image-focal-point="0.5,0.5"
                                      alt="voxdale_logo-1"
                                      data-load="false"
                                      data-image-id="619c0c95a65ad6304c3907c2"
                                      data-type="image"
                                      style={{
                                        left: "0%",
                                        top: "0%",
                                        width: "100%",
                                        height: "100%",
                                        position: "absolute"
                                      }}
                                      data-image-resolution="1000w"
                                      src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/470b10e2-fada-491c-8d98-905f9440be81/voxdale_logo-1.png?format=1000w"
                                    />
                                  </div>
                                </div>
                              </figure>
                            </div>
                          </div>
                        </div>
                        <div
                          className="sqs-block image-block sqs-block-image sqs-text-ready"
                          data-block-type={5}
                          id="block-c6474af3ee92d237e60c"
                        >
                          <div
                            className="sqs-block-content"
                            id="yui_3_17_2_1_1664274854727_225"
                          >
                            <div
                              className="image-block-outer-wrapper layout-caption-below design-layout-inline combination-animation-none individual-animation-none individual-text-animation-none"
                              data-test="image-block-inline-outer-wrapper"
                              id="yui_3_17_2_1_1664274854727_224"
                            >
                              <figure
                                className="sqs-block-image-figure intrinsic"
                                style={{ maxWidth: 295 }}
                                id="yui_3_17_2_1_1664274854727_223"
                              >
                                <div
                                  className="image-block-wrapper preSlide slideIn"
                                  data-animation-role="image"
                                  id="yui_3_17_2_1_1664274854727_222"
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.261818s"
                                  }}
                                >
                                  <div
                                    className="sqs-image-shape-container-element has-aspect-ratio"
                                    style={{
                                      position: "relative",
                                      paddingBottom: "65.08474731445312%",
                                      overflow: "hidden"
                                    }}
                                    id="yui_3_17_2_1_1664274854727_221"
                                  >
                                    <noscript>
                                      &lt;img
                                      src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/8ba0f48c-b81e-4b6c-a821-a4eeb9c9d59c/Screenshot+2021-11-22+222818.png"
                                      alt="Screenshot+2021-11-22+222818"&gt;
                                    </noscript>
                                    <img
                                      className="thumb-image loaded"
                                      data-src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/8ba0f48c-b81e-4b6c-a821-a4eeb9c9d59c/Screenshot+2021-11-22+222818.png"
                                      data-image="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/8ba0f48c-b81e-4b6c-a821-a4eeb9c9d59c/Screenshot+2021-11-22+222818.png"
                                      data-image-dimensions="295x192"
                                      data-image-focal-point="0.5,0.5"
                                      alt="Screenshot+2021-11-22+222818"
                                      data-load="false"
                                      data-image-id="619c0cd33af2966f604c03a2"
                                      data-type="image"
                                      style={{
                                        left: "0%",
                                        top: "0%",
                                        width: "100%",
                                        height: "100%",
                                        position: "absolute"
                                      }}
                                      data-image-resolution="750w"
                                      src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/8ba0f48c-b81e-4b6c-a821-a4eeb9c9d59c/Screenshot+2021-11-22+222818.png?format=750w"
                                    />
                                  </div>
                                </div>
                              </figure>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </section>
            <Caresol />
            <section
              data-test="page-section"
              data-section-theme="black-bold"
              className="page-section layout-engine-section background-width--full-bleed section-height--medium content-width--wide horizontal-alignment--center vertical-alignment--middle black-bold"
              data-section-id="613f32525e18f97349cfc9e9"
              data-controller="SectionWrapperController"
              data-current-styles='{ "imageOverlayOpacity": 0.15, "backgroundWidth": "background-width--full-bleed", "sectionHeight": "section-height--medium", "customSectionHeight": 85, "horizontalAlignment": "horizontal-alignment--center", "verticalAlignment": "vertical-alignment--middle", "contentWidth": "content-width--wide", "sectionTheme": "black-bold", "sectionAnimation": "none", "backgroundMode": "video" }'
              data-current-context='{ "video": { "playbackSpeed": 0.5, "filter": 1, "filterStrength": 0, "zoom": 0, "videoSourceProvider": "none" }, "backgroundImageId": null, "backgroundMediaEffect": null, "typeName": "page" }'
              data-animation="none"
              data-controllers-bound="SectionWrapperController"
              data-active="true"
            >
              <div className="section-background" />
              <div className="content-wrapper" style={{}}>
                <div className="content">
                  <div
                    className="sqs-layout sqs-grid-12 columns-12"
                    data-type="page-section"
                    id="page-section-613f32525e18f97349cfc9e9"
                  >
                    <div className="row sqs-row">
                      <div className="col sqs-col-4 span-4">
                        <div
                          className="sqs-block html-block sqs-block-html"
                          data-block-type={2}
                          id="block-yui_3_17_2_1_1633531729316_28804"
                        >
                          <div className="sqs-block-content">
                            <p
                              className="preFade fadeIn"
                              style={{
                                transitionTimingFunction: "ease",
                                transitionDuration: "0.8s",
                                transitionDelay: "0.550909s"
                              }}
                            >
                              Contact
                            </p>
                          </div>
                        </div>
                        <div
                          className="sqs-block code-block sqs-block-code"
                          data-block-type={23}
                          id="block-yui_3_17_2_1_1633076979246_17404"
                        >
                          <div className="sqs-block-content">
                            <h2
                              className="preSlide slideIn"
                              style={{
                                transitionTimingFunction: "ease",
                                transitionDuration: "0.8s",
                                transitionDelay: "0.556364s"
                              }}
                            >
                              For questions or more information, connect with us
                              via{" "}
                              <span style={{ color: "#FBFF32" }}>
                                info@h-bat.com
                              </span>{" "}
                              or our contact form.
                            </h2>
                          </div>
                        </div>
                        <div
                          className="sqs-block code-block sqs-block-code"
                          data-block-type={23}
                          id="block-yui_3_17_2_1_1633619406010_18556"
                        >
                          <div className="sqs-block-content">
                            <p
                              id="contact-sec"
                              className="preFade fadeIn"
                              style={{
                                transitionTimingFunction: "ease",
                                transitionDuration: "0.8s",
                                transitionDelay: "0.561818s"
                              }}
                            ></p>
                          </div>
                        </div>
                      </div>
                      <div className="col sqs-col-2 span-2">
                        <div
                          className="sqs-block spacer-block sqs-block-spacer sized vsize-1"
                          data-block-type={21}
                          id="block-77c1209ed50b3769feff"
                        >
                          <div className="sqs-block-content">&nbsp;</div>
                        </div>
                      </div>
                      <div className="col sqs-col-6 span-6">
                        <div
                          className="sqs-block form-block sqs-block-form"
                          data-block-type={9}
                          id="block-2466a66d682347393dc2"
                        >
                          <div className="sqs-block-content">
                            <div className="form-wrapper">
                              <div className="form-inner-wrapper">
                                <form
                                  data-form-id="613f32525e18f97349cfc9cb"
                                  data-success-redirect
                                  data-dynamic-strings
                                  autoComplete="on"
                                  method="post"
                                  action="https://etvr.squarespace.com"
                                  noValidate
                                >
                                  <div className="field-list clear">
                                    <fieldset
                                      id="name-yui_3_17_2_1_1596051534885_15441"
                                      className="form-item fields name required"
                                    >
                                      <legend className="title">
                                        Name{" "}
                                        <span
                                          className="required"
                                          aria-hidden="true"
                                        >
                                          *
                                        </span>
                                      </legend>
                                      <div className="field first-name">
                                        <label className="caption">
                                          <input
                                            className="field-element field-control"
                                            name="fname"
                                            x-autocompletetype="given-name"
                                            type="text"
                                            spellCheck="false"
                                            maxLength={30}
                                            data-title="First"
                                            aria-required="true"
                                          />{" "}
                                          <span className="caption-text">
                                            First Name
                                          </span>
                                        </label>
                                      </div>
                                      <div className="field last-name">
                                        <label className="caption">
                                          <input
                                            className="field-element field-control"
                                            name="lname"
                                            x-autocompletetype="surname"
                                            type="text"
                                            spellCheck="false"
                                            maxLength={30}
                                            data-title="Last"
                                            aria-required="true"
                                          />{" "}
                                          <span className="caption-text">
                                            Last Name
                                          </span>
                                        </label>
                                      </div>
                                    </fieldset>
                                    <div
                                      id="email-yui_3_17_2_1_1596051534885_15442"
                                      className="form-item field email required"
                                    >
                                      <label
                                        className="title"
                                        htmlFor="email-yui_3_17_2_1_1596051534885_15442-field"
                                      >
                                        Email{" "}
                                        <span
                                          className="required"
                                          aria-hidden="true"
                                        >
                                          *
                                        </span>
                                      </label>{" "}
                                      <input
                                        className="field-element"
                                        id="email-yui_3_17_2_1_1596051534885_15442-field"
                                        name="email"
                                        type="email"
                                        autoComplete="email"
                                        spellCheck="false"
                                        aria-required="true"
                                      />
                                    </div>
                                    <div
                                      id="textarea-05b7e13a-04ca-4ef1-a88b-2da13bb7395a"
                                      className="form-item field textarea"
                                    >
                                      <label
                                        className="title"
                                        htmlFor="textarea-05b7e13a-04ca-4ef1-a88b-2da13bb7395a-field"
                                      >
                                        Message
                                      </label>
                                      <textarea
                                        className="field-element"
                                        id="textarea-05b7e13a-04ca-4ef1-a88b-2da13bb7395a-field"
                                        defaultValue={""}
                                      />
                                    </div>
                                  </div>
                                  <div
                                    data-animation-role="button"
                                    className="form-button-wrapper form-button-wrapper--align-left preSlide slideIn"
                                    style={{
                                      transitionTimingFunction: "ease",
                                      transitionDuration: "0.8s",
                                      transitionDelay: "0.567273s"
                                    }}
                                  >
                                    <input
                                      className="button sqs-system-button sqs-editable-button sqs-button-element--primary"
                                      type="submit"
                                      defaultValue="SEND"
                                    />
                                  </div>
                                  <div className="hidden form-submission-text">
                                    Thank you!
                                  </div>
                                  <div
                                    className="hidden form-submission-html"
                                    data-submission-html
                                  />
                                </form>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </article>
        </main>
        <footer className="sections" id="footer-sections" data-footer-sections>
          <section
            data-test="page-section"
            data-section-theme="black-bold"
            className="page-section layout-engine-section background-width--full-bleed section-height--small content-width--wide horizontal-alignment--center vertical-alignment--middle black-bold"
            data-section-id="61c1d397e4c2a52ebc9fb555"
            data-controller="SectionWrapperController"
            data-current-styles='{ "imageOverlayOpacity": 0.15, "backgroundWidth": "background-width--full-bleed", "sectionHeight": "section-height--small", "horizontalAlignment": "horizontal-alignment--center", "verticalAlignment": "vertical-alignment--middle", "contentWidth": "content-width--wide", "customContentWidth": 90, "sectionTheme": "black-bold", "sectionAnimation": "none", "backgroundMode": "image" }'
            data-current-context='{ "video": { "playbackSpeed": 0.5, "filter": 1, "filterStrength": 0, "zoom": 0, "videoSourceProvider": "none" }, "backgroundImageId": null, "backgroundMediaEffect": null, "typeName": "page" }'
            data-animation="none"
            data-controllers-bound="SectionWrapperController"
            data-active="true"
          >
            <div className="section-background" />
            <div className="content-wrapper" style={{}}>
              <div className="content">
                <div
                  className="sqs-layout sqs-grid-12 columns-12"
                  data-type="page-section"
                  id="page-section-61c1d397e4c2a52ebc9fb555"
                >
                  <div className="row sqs-row">
                    <div className="col sqs-col-12 span-12">
                      <div className="row sqs-row">
                        <div className="col sqs-col-4 span-4">
                          <div
                            className="sqs-block html-block sqs-block-html"
                            data-block-type={2}
                            id="block-0536b5e1619eaf1f9229"
                          >
                            <div
                              className="sqs-block-content preSlide slideIn"
                              style={{
                                transitionTimingFunction: "ease",
                                transitionDuration: "0.8s",
                                transitionDelay: "0.572727s"
                              }}
                            >
                              <h4
                                style={{
                                  textAlign: "center",
                                  transitionTimingFunction: "ease",
                                  transitionDuration: "0.8s",
                                  transitionDelay: "0.578182s"
                                }}
                                className="preFade fadeIn"
                              >
                                H-BAT
                              </h4>
                            </div>
                          </div>
                        </div>
                        <div className="col sqs-col-8 span-8">
                          <div className="row sqs-row">
                            <div className="col sqs-col-4 span-4">
                              <div
                                className="sqs-block socialaccountlinks-v2-block sqs-block-socialaccountlinks-v2"
                                data-block-type={54}
                                id="block-5c3f605a151c09eff3c4"
                              >
                                <div
                                  className="sqs-block-content preSlide slideIn"
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.583636s"
                                  }}
                                >
                                  <div className="sqs-svg-icon--outer social-icon-alignment-center social-icons-color- social-icons-size-medium social-icons-style-regular">
                                    <nav className="sqs-svg-icon--list">
                                      <a
                                        href="https://facebook.com/etvrproject"
                                        target="_blank"
                                        className="sqs-svg-icon--wrapper facebook-unauth"
                                        aria-label="Facebook"
                                      >
                                        <div>
                                          <svg
                                            className="sqs-svg-icon--social"
                                            viewBox="0 0 64 64"
                                          >
                                            <use
                                              className="sqs-use--icon"
                                              xlinkHref="#facebook-unauth-icon"
                                            />
                                            <use
                                              className="sqs-use--mask"
                                              xlinkHref="#facebook-unauth-mask"
                                            />
                                          </svg>
                                        </div>
                                      </a>{" "}
                                      <a
                                        href="https://www.linkedin.com/company/etvr/"
                                        target="_blank"
                                        className="sqs-svg-icon--wrapper linkedin-unauth"
                                        aria-label="LinkedIn"
                                      >
                                        <div>
                                          <svg
                                            className="sqs-svg-icon--social"
                                            viewBox="0 0 64 64"
                                          >
                                            <use
                                              className="sqs-use--icon"
                                              xlinkHref="#linkedin-unauth-icon"
                                            />
                                            <use
                                              className="sqs-use--mask"
                                              xlinkHref="#linkedin-unauth-mask"
                                            />
                                          </svg>
                                        </div>
                                      </a>{" "}
                                      <a
                                        href="https://twitter.com/ETVRProject"
                                        target="_blank"
                                        className="sqs-svg-icon--wrapper twitter-unauth"
                                        aria-label="Twitter"
                                      >
                                        <div>
                                          <svg
                                            className="sqs-svg-icon--social"
                                            viewBox="0 0 64 64"
                                          >
                                            <use
                                              className="sqs-use--icon"
                                              xlinkHref="#twitter-unauth-icon"
                                            />
                                            <use
                                              className="sqs-use--mask"
                                              xlinkHref="#twitter-unauth-mask"
                                            />
                                          </svg>
                                        </div>
                                      </a>
                                    </nav>
                                  </div>
                                </div>
                              </div>
                            </div>
                            <div className="col sqs-col-4 span-4">
                              <div
                                className="sqs-block html-block sqs-block-html"
                                data-block-type={2}
                                id="block-d2272f2281541b5169d0"
                              >
                                <div
                                  className="sqs-block-content preSlide slideIn"
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.589091s"
                                  }}
                                >
                                  <h4
                                    style={{
                                      textAlign: "center",
                                      transitionTimingFunction: "ease",
                                      transitionDuration: "0.8s",
                                      transitionDelay: "0.594545s"
                                    }}
                                    className="preFade fadeIn"
                                  >
                                    info@h-bat.com
                                  </h4>
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </footer>
      </div>
      <svg
        xmlns="http://www.w3.org/2000/svg"
        version="1.1"
        style={{ display: "none" }}
        data-usage="social-icons-svg"
      >
        <symbol id="facebook-unauth-icon" viewBox="0 0 64 64">
          <path d="M34.1,47V33.3h4.6l0.7-5.3h-5.3v-3.4c0-1.5,0.4-2.6,2.6-2.6l2.8,0v-4.8c-0.5-0.1-2.2-0.2-4.1-0.2 c-4.1,0-6.9,2.5-6.9,7V28H24v5.3h4.6V47H34.1z"></path>
        </symbol>
        <symbol id="facebook-unauth-mask" viewBox="0 0 64 64">
          <path d="M0,0v64h64V0H0z M39.6,22l-2.8,0c-2.2,0-2.6,1.1-2.6,2.6V28h5.3l-0.7,5.3h-4.6V47h-5.5V33.3H24V28h4.6V24 c0-4.6,2.8-7,6.9-7c2,0,3.6,0.1,4.1,0.2V22z"></path>
        </symbol>
        <symbol id="linkedin-unauth-icon" viewBox="0 0 64 64">
          <path d="M20.4,44h5.4V26.6h-5.4V44z M23.1,18c-1.7,0-3.1,1.4-3.1,3.1c0,1.7,1.4,3.1,3.1,3.1 c1.7,0,3.1-1.4,3.1-3.1C26.2,19.4,24.8,18,23.1,18z M39.5,26.2c-2.6,0-4.4,1.4-5.1,2.8h-0.1v-2.4h-5.2V44h5.4v-8.6 c0-2.3,0.4-4.5,3.2-4.5c2.8,0,2.8,2.6,2.8,4.6V44H46v-9.5C46,29.8,45,26.2,39.5,26.2z"></path>
        </symbol>
        <symbol id="linkedin-unauth-mask" viewBox="0 0 64 64">
          <path d="M0,0v64h64V0H0z M25.8,44h-5.4V26.6h5.4V44z M23.1,24.3c-1.7,0-3.1-1.4-3.1-3.1c0-1.7,1.4-3.1,3.1-3.1 c1.7,0,3.1,1.4,3.1,3.1C26.2,22.9,24.8,24.3,23.1,24.3z M46,44h-5.4v-8.4c0-2,0-4.6-2.8-4.6c-2.8,0-3.2,2.2-3.2,4.5V44h-5.4V26.6 h5.2V29h0.1c0.7-1.4,2.5-2.8,5.1-2.8c5.5,0,6.5,3.6,6.5,8.3V44z"></path>
        </symbol>
        <symbol id="twitter-unauth-icon" viewBox="0 0 64 64">
          <path d="M48,22.1c-1.2,0.5-2.4,0.9-3.8,1c1.4-0.8,2.4-2.1,2.9-3.6c-1.3,0.8-2.7,1.3-4.2,1.6 C41.7,19.8,40,19,38.2,19c-3.6,0-6.6,2.9-6.6,6.6c0,0.5,0.1,1,0.2,1.5c-5.5-0.3-10.3-2.9-13.5-6.9c-0.6,1-0.9,2.1-0.9,3.3 c0,2.3,1.2,4.3,2.9,5.5c-1.1,0-2.1-0.3-3-0.8c0,0,0,0.1,0,0.1c0,3.2,2.3,5.8,5.3,6.4c-0.6,0.1-1.1,0.2-1.7,0.2c-0.4,0-0.8,0-1.2-0.1 c0.8,2.6,3.3,4.5,6.1,4.6c-2.2,1.8-5.1,2.8-8.2,2.8c-0.5,0-1.1,0-1.6-0.1c2.9,1.9,6.4,2.9,10.1,2.9c12.1,0,18.7-10,18.7-18.7 c0-0.3,0-0.6,0-0.8C46,24.5,47.1,23.4,48,22.1z"></path>
        </symbol>
        <symbol id="twitter-unauth-mask" viewBox="0 0 64 64">
          <path d="M0,0v64h64V0H0z M44.7,25.5c0,0.3,0,0.6,0,0.8C44.7,35,38.1,45,26.1,45c-3.7,0-7.2-1.1-10.1-2.9 c0.5,0.1,1,0.1,1.6,0.1c3.1,0,5.9-1,8.2-2.8c-2.9-0.1-5.3-2-6.1-4.6c0.4,0.1,0.8,0.1,1.2,0.1c0.6,0,1.2-0.1,1.7-0.2 c-3-0.6-5.3-3.3-5.3-6.4c0,0,0-0.1,0-0.1c0.9,0.5,1.9,0.8,3,0.8c-1.8-1.2-2.9-3.2-2.9-5.5c0-1.2,0.3-2.3,0.9-3.3 c3.2,4,8.1,6.6,13.5,6.9c-0.1-0.5-0.2-1-0.2-1.5c0-3.6,2.9-6.6,6.6-6.6c1.9,0,3.6,0.8,4.8,2.1c1.5-0.3,2.9-0.8,4.2-1.6 c-0.5,1.5-1.5,2.8-2.9,3.6c1.3-0.2,2.6-0.5,3.8-1C47.1,23.4,46,24.5,44.7,25.5z"></path>
        </symbol>
      </svg>
    </>
  );
}
