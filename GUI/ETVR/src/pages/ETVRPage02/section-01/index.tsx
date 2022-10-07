import useWindowSize from "@rehooks/window-size";
import { gsap } from "gsap/all";
import { useEffect, useRef, useState } from "react";

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
    <div
      id="collection-61b3cdb34d3bf66c062b27aa"
      className="header-overlay-alignment-center header-width-full tweak-transparent-header tweak-fixed-header-style-basic tweak-blog-alternating-side-by-side-width-full tweak-blog-alternating-side-by-side-image-aspect-ratio-11-square tweak-blog-alternating-side-by-side-text-alignment-left tweak-blog-alternating-side-by-side-read-more-style-show tweak-blog-alternating-side-by-side-image-text-alignment-middle tweak-blog-alternating-side-by-side-delimiter-bullet tweak-blog-alternating-side-by-side-meta-position-top tweak-blog-alternating-side-by-side-primary-meta-categories tweak-blog-alternating-side-by-side-secondary-meta-date tweak-blog-alternating-side-by-side-excerpt-show tweak-blog-basic-grid-width-inset tweak-blog-basic-grid-image-aspect-ratio-32-standard tweak-blog-basic-grid-text-alignment-left tweak-blog-basic-grid-delimiter-bullet tweak-blog-basic-grid-image-placement-above tweak-blog-basic-grid-read-more-style-show tweak-blog-basic-grid-primary-meta-date tweak-blog-basic-grid-secondary-meta-categories tweak-blog-basic-grid-excerpt-show tweak-blog-item-width-medium tweak-blog-item-text-alignment-center tweak-blog-item-meta-position-above-title tweak-blog-item-show-categories tweak-blog-item-show-date tweak-blog-item-delimiter-bullet tweak-blog-masonry-width-full tweak-blog-masonry-text-alignment-left tweak-blog-masonry-primary-meta-categories tweak-blog-masonry-secondary-meta-date tweak-blog-masonry-meta-position-top tweak-blog-masonry-read-more-style-show tweak-blog-masonry-delimiter-space tweak-blog-masonry-image-placement-above tweak-blog-masonry-excerpt-show tweak-blog-side-by-side-width-full tweak-blog-side-by-side-image-placement-left tweak-blog-side-by-side-image-aspect-ratio-11-square tweak-blog-side-by-side-primary-meta-categories tweak-blog-side-by-side-secondary-meta-date tweak-blog-side-by-side-meta-position-top tweak-blog-side-by-side-text-alignment-left tweak-blog-side-by-side-image-text-alignment-middle tweak-blog-side-by-side-read-more-style-show tweak-blog-side-by-side-delimiter-bullet tweak-blog-side-by-side-excerpt-show tweak-blog-single-column-width-full tweak-blog-single-column-text-alignment-center tweak-blog-single-column-image-placement-above tweak-blog-single-column-delimiter-bullet tweak-blog-single-column-read-more-style-show tweak-blog-single-column-primary-meta-date tweak-blog-single-column-secondary-meta-categories tweak-blog-single-column-meta-position-top tweak-blog-single-column-content-title-only tweak-events-stacked-width-inset tweak-events-stacked-height-small tweak-events-stacked-show-thumbnails tweak-events-stacked-thumbnail-size-23-standard-vertical tweak-events-stacked-date-style-side-tag tweak-events-stacked-show-time tweak-events-stacked-show-location tweak-events-stacked-show-excerpt tweak-global-animations-enabled tweak-global-animations-complexity-level-detailed tweak-global-animations-animation-style-fade tweak-global-animations-animation-type-slide tweak-global-animations-animation-curve-ease tweak-portfolio-grid-basic-width-full tweak-portfolio-grid-basic-height-large tweak-portfolio-grid-basic-image-aspect-ratio-11-square tweak-portfolio-grid-basic-text-alignment-left tweak-portfolio-grid-basic-hover-effect-fade tweak-portfolio-grid-overlay-width-full tweak-portfolio-grid-overlay-height-large tweak-portfolio-grid-overlay-image-aspect-ratio-11-square tweak-portfolio-grid-overlay-text-placement-center tweak-portfolio-grid-overlay-show-text-after-hover tweak-portfolio-index-background-link-format-stacked tweak-portfolio-index-background-width-full tweak-portfolio-index-background-height-large tweak-portfolio-index-background-vertical-alignment-middle tweak-portfolio-index-background-horizontal-alignment-center tweak-portfolio-index-background-delimiter-none tweak-portfolio-index-background-animation-type-fade tweak-portfolio-index-background-animation-duration-medium tweak-portfolio-hover-follow-layout-stacked tweak-portfolio-hover-follow-delimiter-period tweak-portfolio-hover-follow-animation-type-fade tweak-portfolio-hover-follow-animation-duration-medium tweak-portfolio-hover-static-layout-inline tweak-portfolio-hover-static-front tweak-portfolio-hover-static-delimiter-hyphen tweak-portfolio-hover-static-animation-type-fade tweak-portfolio-hover-static-animation-duration-fast tweak-product-basic-item-width-full tweak-product-basic-item-gallery-aspect-ratio-11-square tweak-product-basic-item-text-alignment-left tweak-product-basic-item-navigation-breadcrumbs tweak-product-basic-item-content-alignment-center tweak-product-basic-item-gallery-design-slideshow tweak-product-basic-item-gallery-placement-right tweak-product-basic-item-thumbnail-placement-side tweak-product-basic-item-click-action-none tweak-product-basic-item-hover-action-none tweak-product-basic-item-variant-picker-layout-dropdowns tweak-products-width-full tweak-products-image-aspect-ratio-11-square tweak-products-text-alignment-middle tweak-products-price-show tweak-products-nested-category-type-top tweak-products-category-title tweak-products-header-text-alignment-middle tweak-products-breadcrumbs primary-button-style-outline primary-button-shape-rounded secondary-button-style-outline secondary-button-shape-rounded tertiary-button-style-outline tertiary-button-shape-rounded image-block-poster-text-alignment-center image-block-card-content-position-center image-block-card-text-alignment-left image-block-overlap-content-position-center image-block-overlap-text-alignment-left image-block-collage-content-position-center image-block-collage-text-alignment-left image-block-stack-text-alignment-left hide-opentable-icons opentable-style-dark tweak-product-quick-view-button-style-floating tweak-product-quick-view-button-position-bottom tweak-product-quick-view-lightbox-excerpt-display-truncate tweak-product-quick-view-lightbox-show-arrows tweak-product-quick-view-lightbox-show-close-button tweak-product-quick-view-lightbox-controls-weight-light native-currency-code-usd collection-type-page collection-layout-default collection-61b3cdb34d3bf66c062b27aa mobile-style-available sqs-seven-one seven-one-global-animations"
      tabIndex={-1}
      data-animation-state="booted"
    >
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
          className="header theme-col--primary"
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
                          transitionDelay: "0.0142857s"
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
                        <div className="header-nav-item header-nav-item--collection header-nav-item--active">
                          <a
                            href={`/${end_point}/white-papers`}
                            data-animation-role="header-element"
                            aria-current="page"
                            className="preSlide slideIn"
                            style={{
                              transitionTimingFunction: "ease",
                              transitionDuration: "0.8s",
                              transitionDelay: "0.0285714s"
                            }}
                          >
                            White Papers
                          </a>
                        </div>
                        <div className="header-nav-item header-nav-item--collection header-nav-item--homepage">
                          <a
                            href={`/${end_point}`}
                            data-animation-role="header-element"
                            className="preSlide slideIn"
                            style={{
                              transitionTimingFunction: "ease",
                              transitionDuration: "0.8s",
                              transitionDelay: "0.0428571s"
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
                <div className="language-picker-content">
                  <div className="language-item">
                    <a href="#"><span>العربية‏</span></a>
                  </div>
                  <div className="language-item">
                    <a href="#"><span>English</span></a>
                  </div>
                </div>
              </div>
              <div className="showOnMobile" />
              <div className="showOnDesktop" />
            </div> */}
                <style
                  dangerouslySetInnerHTML={{
                    __html:
                      "\n                .top-bun,\n                .patty,\n                .bottom-bun {\n                  height: 3px;\n                }\n              "
                  }}
                />
                {/* Burger */}
                <div
                  className="header-burger menu-overlay-has-visible-non-navigation-items no-actions preSlide slideIn"
                  data-animation-role="header-element"
                  style={{
                    transitionTimingFunction: "ease",
                    transitionDuration: "0.8s",
                    transitionDelay: "0.0571429s"
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
                      transitionDelay: "0.0714286s"
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
                          transitionDelay: "0.0857143s"
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
                        <div className="header-nav-item header-nav-item--collection header-nav-item--active">
                          <a
                            href={`/${end_point}/white-papers`}
                            data-animation-role="header-element"
                            aria-current="page"
                            className="preSlide slideIn"
                            style={{
                              transitionTimingFunction: "ease",
                              transitionDuration: "0.8s",
                              transitionDelay: "0.1s"
                            }}
                          >
                            White Papers
                          </a>
                        </div>
                        <div className="header-nav-item header-nav-item--collection header-nav-item--homepage">
                          <a
                            href={`/${end_point}`}
                            data-animation-role="header-element"
                            className="preSlide slideIn"
                            style={{
                              transitionTimingFunction: "ease",
                              transitionDuration: "0.8s",
                              transitionDelay: "0.114286s"
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
                      "\n                .top-bun,\n                .patty,\n                .bottom-bun {\n                  height: 3px;\n                }\n              "
                  }}
                />
                {/* Burger */}
                <div
                  className="header-burger menu-overlay-has-visible-non-navigation-items no-actions preSlide slideIn"
                  data-animation-role="header-element"
                  style={{
                    transitionTimingFunction: "ease",
                    transitionDuration: "0.8s",
                    transitionDelay: "0.128571s"
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
                    <div className="container header-menu-nav-item header-menu-nav-item--collection header-menu-nav-item--active">
                      <a
                        href={`/${end_point}/white-papers`}
                        aria-current="page"
                      >
                        <div className="header-menu-nav-item-content">
                          White Papers
                        </div>
                      </a>
                    </div>
                    <div className="container header-menu-nav-item header-menu-nav-item--collection header-menu-nav-item--homepage">
                      <a href={`/${end_point}`}>
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
                {/* <div id="multilingual-language-picker-mobile" className="header-menu-nav-folder" data-folder="language-picker">
              <div className="header-menu-nav-folder-content">
                <div className="header-menu-controls header-menu-nav-item">
                  <a className="header-menu-controls-control header-menu-controls-control--active" data-action="back" href="/" tabIndex={-1}><span>Back</span></a>
                </div>
                <div className="language-picker-content">
                  <div className="header-menu-nav-item">
                    <a href="#"><span>العربية‏</span></a>
                  </div>
                  <div className="header-menu-nav-item">
                    <a href="#"><span>English</span></a>
                  </div>
                </div>
              </div>
            </div> */}
              </nav>
            </div>
          </div>
        </header>
        <main id="page" className="container" role="main">
          <article
            className="sections"
            data-page-sections="61b3cdb34d3bf66c062b27a9"
            id="sections"
          >
            <section
              data-test="page-section"
              data-section-theme
              className="page-section layout-engine-section background-width--full-bleed section-height--small content-width--medium horizontal-alignment--center vertical-alignment--middle"
              data-section-id="61b3cdb34d3bf66c062b27ac"
              data-controller="SectionWrapperController"
              data-current-styles='{ "imageOverlayOpacity": 0.15, "backgroundWidth": "background-width--full-bleed", "sectionHeight": "section-height--small", "horizontalAlignment": "horizontal-alignment--center", "verticalAlignment": "vertical-alignment--middle", "contentWidth": "content-width--medium", "sectionTheme": "", "sectionAnimation": "none", "backgroundMode": "image" }'
              data-current-context='{ "video": { "playbackSpeed": 0.5, "filter": 1, "filterStrength": 0, "zoom": 0, "videoSourceProvider": "none" }, "backgroundImageId": null, "backgroundMediaEffect": null, "typeName": "page" }'
              data-animation="none"
              style={{ paddingTop: "196.922px" }}
              data-controllers-bound="SectionWrapperController"
              id="yui_3_17_2_1_1664277080514_100"
              data-active="true"
            >
              <div className="section-background" />
              <div
                className="content-wrapper"
                style={{}}
                id="yui_3_17_2_1_1664277080514_99"
              >
                <div className="content" id="yui_3_17_2_1_1664277080514_98">
                  <div
                    className="sqs-layout sqs-grid-12 columns-12"
                    data-type="page-section"
                    id="page-section-61b3cdb34d3bf66c062b27ac"
                  >
                    <div
                      className="row sqs-row"
                      id="yui_3_17_2_1_1664277080514_97"
                    >
                      <div
                        className="col sqs-col-12 span-12"
                        id="yui_3_17_2_1_1664277080514_96"
                      >
                        <div
                          className="sqs-block html-block sqs-block-html"
                          data-block-type={2}
                          id="block-340add4414286e0f7ed3"
                        >
                          <div className="sqs-block-content">
                            <h1
                              style={{
                                textAlign: "center",
                                transitionTimingFunction: "ease",
                                transitionDuration: "0.8s",
                                transitionDelay: "0.142857s"
                              }}
                              className="preSlide slideIn"
                            >
                              Introducing H-BAT
                            </h1>
                            <p
                              style={{
                                textAlign: "center",
                                transitionTimingFunction: "ease",
                                transitionDuration: "0.8s",
                                transitionDelay: "0.157143s"
                              }}
                              className="preFade fadeIn"
                            >
                              Below is a collection of our most recent
                              <br />
                              White Papers.
                            </p>
                          </div>
                        </div>
                        <div
                          className="sqs-block image-block sqs-block-image sqs-text-ready"
                          data-block-type={5}
                          id="block-5b3316d416370cbf4b15"
                        >
                          <div
                            className="sqs-block-content"
                            id="yui_3_17_2_1_1664277080514_95"
                          >
                            <div
                              className="image-block-outer-wrapper layout-caption-below design-layout-inline combination-animation-none individual-animation-none individual-text-animation-none"
                              data-test="image-block-inline-outer-wrapper"
                              id="yui_3_17_2_1_1664277080514_94"
                            >
                              <figure
                                className="sqs-block-image-figure intrinsic"
                                style={{ maxWidth: 574 }}
                                id="yui_3_17_2_1_1664277080514_93"
                              >
                                <div
                                  className="image-block-wrapper preSlide slideIn"
                                  data-animation-role="image"
                                  id="yui_3_17_2_1_1664277080514_92"
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.171429s"
                                  }}
                                >
                                  <div
                                    className="sqs-image-shape-container-element has-aspect-ratio"
                                    style={{
                                      position: "relative",
                                      paddingBottom: "70.20906066894531%",
                                      overflow: "hidden"
                                    }}
                                    id="yui_3_17_2_1_1664277080514_91"
                                  >
                                    <noscript>
                                      &lt;img
                                      src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/0cd89b46-8736-4d70-b1d8-0477630414bc/Screenshot+2021-11-24+174658.png"
                                      alt="Screenshot+2021-11-24+174658"&gt;
                                    </noscript>
                                    <img
                                      className="thumb-image loaded"
                                      data-src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/0cd89b46-8736-4d70-b1d8-0477630414bc/Screenshot+2021-11-24+174658.png"
                                      data-image="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/0cd89b46-8736-4d70-b1d8-0477630414bc/Screenshot+2021-11-24+174658.png"
                                      data-image-dimensions="574x403"
                                      data-image-focal-point="0.5,0.5"
                                      alt="Screenshot+2021-11-24+174658"
                                      data-load="false"
                                      data-image-id="61b3ce6ae09e1965e7bf8ab8"
                                      data-type="image"
                                      style={{
                                        left: "0%",
                                        top: "0%",
                                        width: "100%",
                                        height: "100%",
                                        position: "absolute"
                                      }}
                                      data-image-resolution="1500w"
                                      src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/0cd89b46-8736-4d70-b1d8-0477630414bc/Screenshot+2021-11-24+174658.png?format=1500w"
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
                                        transitionDelay: "0.185714s"
                                      }}
                                      className="preFade fadeIn"
                                    >
                                      110V 17A - 1.8kW - 5kWh concept unit
                                    </p>
                                  </div>
                                </figcaption>
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
              data-section-theme="black-bold"
              className="page-section layout-engine-section background-width--full-bleed content-width--wide horizontal-alignment--center vertical-alignment--middle black-bold"
              data-section-id="61b3cdb34d3bf66c062b27ae"
              data-controller="SectionWrapperController"
              data-current-styles='{ "imageOverlayOpacity": 0.15, "backgroundWidth": "background-width--full-bleed", "sectionHeight": "section-height--custom", "customSectionHeight": 50, "horizontalAlignment": "horizontal-alignment--center", "verticalAlignment": "vertical-alignment--middle", "contentWidth": "content-width--wide", "sectionTheme": "black-bold", "sectionAnimation": "none", "backgroundMode": "image" }'
              data-current-context='{ "video": { "playbackSpeed": 0.5, "filter": 1, "filterStrength": 0, "zoom": 0, "videoSourceProvider": "none" }, "backgroundImageId": null, "backgroundMediaEffect": null, "typeName": "page" }'
              data-animation="none"
              style={{ minHeight: "50vh" }}
              data-controllers-bound="SectionWrapperController"
              data-active="true"
            >
              <div className="section-background" />
              <div
                className="content-wrapper"
                style={{
                  paddingTop: "calc(50vmax / 10)",
                  paddingBottom: "calc(50vmax / 10)"
                }}
              >
                <div className="content">
                  <div
                    className="sqs-layout sqs-grid-12 columns-12"
                    data-type="page-section"
                    id="page-section-61b3cdb34d3bf66c062b27ae"
                  >
                    <div className="row sqs-row">
                      <div className="col sqs-col-12 span-12">
                        <div
                          className="sqs-block html-block sqs-block-html"
                          data-block-type={2}
                          id="block-5fc7cc747e86afddbf61"
                        >
                          <div className="sqs-block-content">
                            <h1
                              style={{
                                textAlign: "center",
                                transitionTimingFunction: "ease",
                                transitionDuration: "0.8s",
                                transitionDelay: "0.2s"
                              }}
                              className="preSlide slideIn"
                            >
                              White Papers
                            </h1>
                          </div>
                        </div>
                        <div
                          className="sqs-block spacer-block sqs-block-spacer sized vsize-1"
                          data-aspect-ratio="1.5714285714285714"
                          data-block-type={21}
                          id="block-dfedc2101f052bacefcc"
                        >
                          <div
                            className="sqs-block-content sqs-intrinsic"
                            id="yui_3_17_2_1_1664277080514_116"
                            style={{ paddingBottom: "1.57143%" }}
                          >
                            &nbsp;
                          </div>
                        </div>
                        <div className="row sqs-row">
                          <div className="col sqs-col-4 span-4">
                            <div
                              className="sqs-block html-block sqs-block-html"
                              data-block-type={2}
                              id="block-0d2099d7e0ff6f578f19"
                            >
                              <div className="sqs-block-content">
                                <h4
                                  style={{
                                    textAlign: "center",
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.214286s"
                                  }}
                                  className="preFade fadeIn"
                                >
                                  H-BAT in Buses
                                </h4>
                              </div>
                            </div>
                            <div
                              className="sqs-block embed-block sqs-block-embed"
                              data-block-json='{"hSize":null,"floatDir":null,"url":"https://www.slideshare.net/Zacariah1/etvr-in-busses","html":"<iframe src=\"https://www.slideshare.net/slideshow/embed_code/key/oji7hBvxzMXU6X\" width=\"479\" height=\"511\" frameborder=\"0\" marginwidth=\"0\" marginheight=\"0\" scrolling=\"no\" style=\"border:1px solid #CCC; border-width:1px; margin-bottom:5px; max-width: 100%;\" allowfullscreen> </iframe> <div style=\"margin-bottom:5px\"> <strong> <a href=\"https://www.slideshare.net/Zacariah1/etvr-in-busses\" title=\"H-Bat in Busses\" target=\"_blank\">H-Bat in Busses</a> </strong> from <strong><a href=\"https://www.slideshare.net/Zacariah1\" target=\"_blank\">Zacariah1</a></strong> </div>","width":477,"height":510,"resolvedBy":"slideshare","providerName":"SlideShare","thumbnailUrl":"https://cdn.slidesharecdn.com/ss_thumbnails/14-211122215801-thumbnail.jpg?cb=1637619033"}'
                              data-block-type={22}
                              id="block-yui_3_17_2_1_1639173574079_32638"
                            >
                              <div
                                className="sqs-block-content"
                                id="yui_3_17_2_1_1664277080514_67"
                              >
                                <div
                                  className="intrinsic"
                                  style={{ maxWidth: "100%" }}
                                >
                                  <div
                                    className="embed-block-wrapper embed-block-provider-SlideShare"
                                    style={{ paddingBottom: "106.91824%" }}
                                  >
                                    <iframe
                                      marginWidth={0}
                                      scrolling="no"
                                      data-image-dimensions="477x510"
                                      allowFullScreen
                                      src="https://www.slideshare.net/slideshow/embed_code/key/oji7hBvxzMXU6X?wmode=opaque"
                                      width={479}
                                      data-embed="true"
                                      frameBorder={0}
                                      style={{
                                        border: "1px solid #CCC",
                                        borderWidth: 1,
                                        marginBottom: 5,
                                        maxWidth: "100%"
                                      }}
                                      marginHeight={0}
                                      height={511}
                                    />
                                    <div style={{ marginBottom: 5 }}>
                                      <strong>
                                        <a
                                          href="https://www.slideshare.net/Zacariah1/etvr-in-busses"
                                          title="H-Bat in Busses"
                                          target="_blank"
                                        >
                                          H-Bat in Busses
                                        </a>
                                      </strong>{" "}
                                      from
                                      <strong>
                                        <a
                                          href="https://www.slideshare.net/Zacariah1"
                                          target="_blank"
                                        >
                                          Zacariah1
                                        </a>
                                      </strong>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                          <div className="col sqs-col-4 span-4">
                            <div
                              className="sqs-block html-block sqs-block-html"
                              data-block-type={2}
                              id="block-957d6856f713f2ec3ac2"
                            >
                              <div className="sqs-block-content">
                                <h4
                                  style={{
                                    textAlign: "center",
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.228571s"
                                  }}
                                  className="preFade fadeIn"
                                >
                                  H-BAT in Scooters
                                </h4>
                              </div>
                            </div>
                            <div
                              className="sqs-block embed-block sqs-block-embed"
                              data-block-json='{"hSize":null,"floatDir":null,"url":"https://www.slideshare.net/Zacariah1/etvr-in-escooters","html":"<iframe src=\"https://www.slideshare.net/slideshow/embed_code/key/Fs24EiTPBJ9QRD\" width=\"479\" height=\"511\" frameborder=\"0\" marginwidth=\"0\" marginheight=\"0\" scrolling=\"no\" style=\"border:1px solid #CCC; border-width:1px; margin-bottom:5px; max-width: 100%;\" allowfullscreen> </iframe> <div style=\"margin-bottom:5px\"> <strong> <a href=\"https://www.slideshare.net/Zacariah1/etvr-in-escooters\" title=\" h-bat in e-scooters\" target=\"_blank\"> h-bat in e-scooters</a> </strong> from <strong><a href=\"https://www.slideshare.net/Zacariah1\" target=\"_blank\">Zacariah1</a></strong> </div>","width":477,"height":510,"resolvedBy":"slideshare","providerName":"SlideShare","thumbnailUrl":"https://cdn.slidesharecdn.com/ss_thumbnails/h-bat-211122215808-thumbnail.jpg?cb=1637619169"}'
                              data-block-type={22}
                              id="block-yui_3_17_2_1_1639173574079_35766"
                            >
                              <div
                                className="sqs-block-content"
                                id="yui_3_17_2_1_1664277080514_72"
                              >
                                <div
                                  className="intrinsic"
                                  style={{ maxWidth: "100%" }}
                                >
                                  <div
                                    className="embed-block-wrapper embed-block-provider-SlideShare"
                                    style={{ paddingBottom: "106.91824%" }}
                                  >
                                    <iframe
                                      marginWidth={0}
                                      scrolling="no"
                                      data-image-dimensions="477x510"
                                      allowFullScreen
                                      src="https://www.slideshare.net/slideshow/embed_code/key/Fs24EiTPBJ9QRD?wmode=opaque"
                                      width={479}
                                      data-embed="true"
                                      frameBorder={0}
                                      style={{
                                        border: "1px solid #CCC",
                                        borderWidth: 1,
                                        marginBottom: 5,
                                        maxWidth: "100%"
                                      }}
                                      marginHeight={0}
                                      height={511}
                                    />
                                    <div style={{ marginBottom: 5 }}>
                                      <strong>
                                        <a
                                          href="https://www.slideshare.net/Zacariah1/etvr-in-escooters"
                                          title=" h-bat in e-scooters"
                                          target="_blank"
                                        >
                                          h-bat in e-scooters
                                        </a>
                                      </strong>
                                      from{" "}
                                      <strong>
                                        <a
                                          href="https://www.slideshare.net/Zacariah1"
                                          target="_blank"
                                        >
                                          Zacariah1
                                        </a>
                                      </strong>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                          <div className="col sqs-col-4 span-4">
                            <div
                              className="sqs-block html-block sqs-block-html"
                              data-block-type={2}
                              id="block-533665b10856350cd587"
                            >
                              <div className="sqs-block-content">
                                <h4
                                  style={{
                                    textAlign: "center",
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.242857s"
                                  }}
                                  className="preFade fadeIn"
                                >
                                  Interested in our R&amp;D?
                                </h4>
                              </div>
                            </div>
                            <div
                              className="sqs-block embed-block sqs-block-embed"
                              data-block-json='{"hSize":null,"floatDir":null,"url":"https://www.slideshare.net/Zacariah1/h-bat-potential","html":"<iframe src=\"https://www.slideshare.net/slideshow/embed_code/key/6UzqoxeVRh41Ko\" width=\"479\" height=\"511\" frameborder=\"0\" marginwidth=\"0\" marginheight=\"0\" scrolling=\"no\" style=\"border:1px solid #CCC; border-width:1px; margin-bottom:5px; max-width: 100%;\" allowfullscreen> </iframe> <div style=\"margin-bottom:5px\"> <strong> <a href=\"https://www.slideshare.net/Zacariah1/h-bat-potential\" title=\"H bat potential\" target=\"_blank\">H bat potential</a> </strong> from <strong><a href=\"https://www.slideshare.net/Zacariah1\" target=\"_blank\">Zacariah1</a></strong> </div>","width":477,"height":510,"resolvedBy":"slideshare","providerName":"SlideShare","thumbnailUrl":"https://cdn.slidesharecdn.com/ss_thumbnails/h-batpotential-211122215804-thumbnail.jpg?cb=1637619277"}'
                              data-block-type={22}
                              id="block-yui_3_17_2_1_1639173574079_36701"
                            >
                              <div
                                className="sqs-block-content"
                                id="yui_3_17_2_1_1664277080514_77"
                              >
                                <div
                                  className="intrinsic"
                                  style={{ maxWidth: "100%" }}
                                >
                                  <div
                                    className="embed-block-wrapper embed-block-provider-SlideShare"
                                    style={{ paddingBottom: "106.91824%" }}
                                  >
                                    <iframe
                                      marginWidth={0}
                                      scrolling="no"
                                      data-image-dimensions="477x510"
                                      allowFullScreen
                                      src="https://www.slideshare.net/slideshow/embed_code/key/6UzqoxeVRh41Ko?wmode=opaque"
                                      width={479}
                                      data-embed="true"
                                      frameBorder={0}
                                      style={{
                                        border: "1px solid #CCC",
                                        borderWidth: 1,
                                        marginBottom: 5,
                                        maxWidth: "100%"
                                      }}
                                      marginHeight={0}
                                      height={511}
                                    />
                                    <div style={{ marginBottom: 5 }}>
                                      <strong>
                                        <a
                                          href="https://www.slideshare.net/Zacariah1/h-bat-potential"
                                          title="H bat potential"
                                          target="_blank"
                                        >
                                          H bat potential
                                        </a>
                                      </strong>{" "}
                                      from
                                      <strong>
                                        <a
                                          href="https://www.slideshare.net/Zacariah1"
                                          target="_blank"
                                        >
                                          Zacariah1
                                        </a>
                                      </strong>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                        <div
                          className="sqs-block spacer-block sqs-block-spacer sized vsize-1"
                          data-aspect-ratio="1.5714285714285714"
                          data-block-type={21}
                          id="block-54ef441d223aecec7778"
                        >
                          <div
                            className="sqs-block-content sqs-intrinsic"
                            id="yui_3_17_2_1_1664277080514_119"
                            style={{ paddingBottom: "1.57143%" }}
                          >
                            &nbsp;
                          </div>
                        </div>
                        <div className="row sqs-row">
                          <div className="col sqs-col-4 span-4">
                            <div
                              className="sqs-block html-block sqs-block-html"
                              data-block-type={2}
                              id="block-2f8cda3285713fecc6f5"
                            >
                              <div className="sqs-block-content">
                                <h4
                                  style={{
                                    textAlign: "center",
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.257143s"
                                  }}
                                  className="preFade fadeIn"
                                >
                                  Current H-BAT Specification
                                </h4>
                              </div>
                            </div>
                            <div
                              className="sqs-block embed-block sqs-block-embed"
                              data-block-json='{"hSize":null,"floatDir":null,"url":"https://www.slideshare.net/Zacariah1/h-bat-mvp-specifications","html":"<iframe src=\"https://www.slideshare.net/slideshow/embed_code/key/Cv9iPZ3FZOkHPm\" width=\"479\" height=\"511\" frameborder=\"0\" marginwidth=\"0\" marginheight=\"0\" scrolling=\"no\" style=\"border:1px solid #CCC; border-width:1px; margin-bottom:5px; max-width: 100%;\" allowfullscreen> </iframe> <div style=\"margin-bottom:5px\"> <strong> <a href=\"https://www.slideshare.net/Zacariah1/h-bat-mvp-specifications\" title=\"H bat mvp specifications\" target=\"_blank\">H bat mvp specifications</a> </strong> from <strong><a href=\"https://www.slideshare.net/Zacariah1\" target=\"_blank\">Zacariah1</a></strong> </div>","width":477,"height":510,"resolvedBy":"slideshare","providerName":"SlideShare","thumbnailUrl":"https://cdn.slidesharecdn.com/ss_thumbnails/h-batmvpspecifications-211122215801-thumbnail.jpg?cb=1637619448"}'
                              data-block-type={22}
                              id="block-yui_3_17_2_1_1639173574079_37668"
                            >
                              <div
                                className="sqs-block-content"
                                id="yui_3_17_2_1_1664277080514_82"
                              >
                                <div
                                  className="intrinsic"
                                  style={{ maxWidth: "100%" }}
                                >
                                  <div
                                    className="embed-block-wrapper embed-block-provider-SlideShare"
                                    style={{ paddingBottom: "106.91824%" }}
                                  >
                                    <iframe
                                      marginWidth={0}
                                      scrolling="no"
                                      data-image-dimensions="477x510"
                                      allowFullScreen
                                      src="https://www.slideshare.net/slideshow/embed_code/key/Cv9iPZ3FZOkHPm?wmode=opaque"
                                      width={479}
                                      data-embed="true"
                                      frameBorder={0}
                                      style={{
                                        border: "1px solid #CCC",
                                        borderWidth: 1,
                                        marginBottom: 5,
                                        maxWidth: "100%"
                                      }}
                                      marginHeight={0}
                                      height={511}
                                    />
                                    <div style={{ marginBottom: 5 }}>
                                      <strong>
                                        <a
                                          href="https://www.slideshare.net/Zacariah1/h-bat-mvp-specifications"
                                          title="H bat mvp specifications"
                                          target="_blank"
                                        >
                                          H bat mvp specifications
                                        </a>
                                      </strong>{" "}
                                      from{" "}
                                      <strong>
                                        <a
                                          href="https://www.slideshare.net/Zacariah1"
                                          target="_blank"
                                        >
                                          Zacariah1
                                        </a>
                                      </strong>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                          <div className="col sqs-col-4 span-4" />
                          <div className="col sqs-col-4 span-4">
                            <div
                              className="sqs-block html-block sqs-block-html"
                              data-block-type={2}
                              id="block-986e8f6e2ebba14a8233"
                            >
                              <div className="sqs-block-content">
                                <h4
                                  style={{
                                    textAlign: "center",
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.271429s"
                                  }}
                                  className="preFade fadeIn"
                                >
                                  H-BAT Prototype Specification
                                </h4>
                              </div>
                            </div>
                            <div
                              className="sqs-block embed-block sqs-block-embed"
                              data-block-json='{"hSize":null,"floatDir":null,"url":"https://www.slideshare.net/Zacariah1/mvp-specifications","html":"<iframe src=\"https://www.slideshare.net/slideshow/embed_code/key/cUGYnn53VTj9dO\" width=\"479\" height=\"511\" frameborder=\"0\" marginwidth=\"0\" marginheight=\"0\" scrolling=\"no\" style=\"border:1px solid #CCC; border-width:1px; margin-bottom:5px; max-width: 100%;\" allowfullscreen> </iframe> <div style=\"margin-bottom:5px\"> <strong> <a href=\"https://www.slideshare.net/Zacariah1/mvp-specifications\" title=\"Mvp specifications\" target=\"_blank\">Mvp specifications</a> </strong> from <strong><a href=\"https://www.slideshare.net/Zacariah1\" target=\"_blank\">Zacariah1</a></strong> </div>","width":477,"height":510,"resolvedBy":"slideshare","providerName":"SlideShare","thumbnailUrl":"https://cdn.slidesharecdn.com/ss_thumbnails/mvpspecifications-211122215808-thumbnail.jpg?cb=1637619521"}'
                              data-block-type={22}
                              id="block-yui_3_17_2_1_1639173574079_38674"
                            >
                              <div
                                className="sqs-block-content"
                                id="yui_3_17_2_1_1664277080514_87"
                              >
                                <div
                                  className="intrinsic"
                                  style={{ maxWidth: "100%" }}
                                >
                                  <div
                                    className="embed-block-wrapper embed-block-provider-SlideShare"
                                    style={{ paddingBottom: "106.91824%" }}
                                  >
                                    <iframe
                                      marginWidth={0}
                                      scrolling="no"
                                      data-image-dimensions="477x510"
                                      allowFullScreen
                                      src="https://www.slideshare.net/slideshow/embed_code/key/cUGYnn53VTj9dO?wmode=opaque"
                                      width={479}
                                      data-embed="true"
                                      frameBorder={0}
                                      style={{
                                        border: "1px solid #CCC",
                                        borderWidth: 1,
                                        marginBottom: 5,
                                        maxWidth: "100%"
                                      }}
                                      marginHeight={0}
                                      height={511}
                                    />
                                    <div style={{ marginBottom: 5 }}>
                                      <strong>
                                        <a
                                          href="https://www.slideshare.net/Zacariah1/mvp-specifications"
                                          title="Mvp specifications"
                                          target="_blank"
                                        >
                                          Mvp specifications
                                        </a>
                                      </strong>{" "}
                                      from
                                      <strong>
                                        <a
                                          href="https://www.slideshare.net/Zacariah1"
                                          target="_blank"
                                        >
                                          Zacariah1
                                        </a>
                                      </strong>
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
              </div>
            </section>
            <section
              data-test="page-section"
              data-section-theme="white"
              className="page-section layout-engine-section background-width--inset section-height--large content-width--medium horizontal-alignment--center vertical-alignment--middle has-background white"
              data-section-id="61b3e49c1f9f98697525630e"
              data-controller="SectionWrapperController"
              data-current-styles='{ "backgroundImage": { "id": "61b3e5423d1a4b13b9683bf8", "recordType": 2, "addedOn": 1639179586093, "updatedOn": 1639179586146, "workflowState": 1, "publishOn": 1639179586093, "authorId": "617ab393b49a9d769760fc22", "systemDataId": "a971f900-5237-46c6-b953-92657b9c8a17", "systemDataVariants": "2119x805,100w,300w,500w,750w,1000w,1500w", "systemDataSourceType": "JPG", "filename": "comparison.jpg", "mediaFocalPoint": { "x": 0.5, "y": 0.5, "source": 3 }, "colorData": { "topLeftAverage": "f8f9fb", "topRightAverage": "f8f9fb", "bottomLeftAverage": "f8f9fb", "bottomRightAverage": "f8f9fb", "centerAverage": "eeeff1", "suggestedBgColor": "f3f4f6" }, "urlId": "8peglzubj6oliqkd891jipmq33xasu", "title": "", "body": null, "likeCount": 0, "commentCount": 0, "publicCommentCount": 0, "commentState": 2, "unsaved": false, "author": { "id": "617ab393b49a9d769760fc22", "displayName": "Zacariah Heim", "firstName": "Zacariah", "lastName": "Heim", "bio": "" }, "assetUrl": "https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/a971f900-5237-46c6-b953-92657b9c8a17/comparison.jpg", "contentType": "image/jpeg", "items": [ ], "pushedServices": { }, "pendingPushedServices": { }, "recordTypeLabel": "image", "originalSize": "2119x805" }, "imageOverlayOpacity": 0.15, "backgroundWidth": "background-width--inset", "sectionHeight": "section-height--large", "customSectionHeight": 85, "horizontalAlignment": "horizontal-alignment--center", "verticalAlignment": "vertical-alignment--middle", "contentWidth": "content-width--medium", "sectionTheme": "white", "sectionAnimation": "none", "backgroundMode": "image" }'
              data-current-context='{ "video": { "playbackSpeed": 0.5, "filter": 1, "filterStrength": 0, "zoom": 0, "videoSourceProvider": "none" }, "backgroundImageId": null, "backgroundMediaEffect": null, "typeName": "page" }'
              data-animation="none"
              data-controllers-bound="SectionWrapperController"
              data-active="true"
            >
              <div className="section-background">
                <img
                  alt="comparison"
                  data-src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/a971f900-5237-46c6-b953-92657b9c8a17/comparison.jpg"
                  data-image="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/a971f900-5237-46c6-b953-92657b9c8a17/comparison.jpg"
                  data-image-dimensions="2119x805"
                  data-image-focal-point="0.5,0.5"
                  data-load="false"
                  style={{
                    width: "100%",
                    height: "100%",
                    objectPosition: "50% 50%",
                    objectFit: "cover"
                  }}
                  data-parent-ratio="2.2"
                  data-image-resolution="2500w"
                  src="https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/a971f900-5237-46c6-b953-92657b9c8a17/comparison.jpg?format=2500w"
                />
                <div
                  className="section-background-overlay"
                  style={{ opacity: "0.15" }}
                />
              </div>
              <div className="content-wrapper" style={{}}>
                <div className="content">
                  <div
                    className="sqs-layout sqs-grid-12 columns-12"
                    data-type="page-section"
                    id="page-section-61b3e49c1f9f98697525630e"
                  >
                    <div className="row sqs-row">
                      <div className="col sqs-col-12 span-12">
                        <div
                          className="sqs-block spacer-block sqs-block-spacer sized vsize-1"
                          data-block-type={21}
                          id="block-896a2f6e36880e3d79da"
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
              data-section-theme
              className="page-section layout-engine-section background-width--inset section-height--medium content-width--wide horizontal-alignment--center vertical-alignment--middle"
              data-section-id="61b3d6fec5c1000e554ca446"
              data-controller="SectionWrapperController"
              data-current-styles='{ "imageOverlayOpacity": 0.15, "backgroundWidth": "background-width--inset", "sectionHeight": "section-height--medium", "horizontalAlignment": "horizontal-alignment--center", "verticalAlignment": "vertical-alignment--middle", "contentWidth": "content-width--wide", "sectionAnimation": "none", "backgroundMode": "image" }'
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
                    id="page-section-61b3d6fec5c1000e554ca446"
                  >
                    <div className="row sqs-row">
                      <div className="col sqs-col-12 span-12">
                        <div
                          className="sqs-block html-block sqs-block-html"
                          data-block-type={2}
                          id="block-670c2226ae236d6e88f8"
                        >
                          <div className="sqs-block-content">
                            <h2
                              style={{
                                textAlign: "center",
                                transitionTimingFunction: "ease",
                                transitionDuration: "0.8s",
                                transitionDelay: "0.285714s"
                              }}
                              className="preSlide slideIn"
                            >
                              H-Bat FAQ’s
                            </h2>
                          </div>
                        </div>
                        <div
                          className="sqs-block spacer-block sqs-block-spacer sized vsize-1"
                          data-block-type={21}
                          id="block-e0cdb752e160d1de7d9d"
                        >
                          <div className="sqs-block-content">&nbsp;</div>
                        </div>
                        <div className="row sqs-row">
                          <div className="col sqs-col-4 span-4">
                            <div
                              className="sqs-block html-block sqs-block-html"
                              data-block-type={2}
                              id="block-8e639b2620966274a8d5"
                            >
                              <div className="sqs-block-content">
                                <h4
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.3s"
                                  }}
                                  className="preFade fadeIn"
                                >
                                  What is H-Bat?
                                </h4>
                                <p
                                  className="sqsrte-small preFade fadeIn"
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.314286s"
                                  }}
                                >
                                  H-Bat stands for Hydrogen-Battery. Using
                                  recent advances in nano-materials sciences,
                                  our team has designed a technology that is a
                                  unique hybrid of well-known classical systems.
                                  Namely a; Fuel Cell, Electrolyzer, and
                                  Hydrogen Storage Medium. All in one device.
                                </p>
                                <p
                                  className="preFade fadeIn"
                                  data-rte-preserve-empty="true"
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.328571s"
                                  }}
                                ></p>
                                <h4
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.342857s"
                                  }}
                                  className="preFade fadeIn"
                                >
                                  How is this different than a typical Fuel Cell
                                  or Battery?
                                </h4>
                                <p
                                  className="sqsrte-small preFade fadeIn"
                                  style={{
                                    transitionTimingFunction: "ease",
                                    transitionDuration: "0.8s",
                                    transitionDelay: "0.357143s"
                                  }}
                                >
                                  Your typical Fuel Cell system will first pass
                                  a hydrogen donor fuel (typically water) to an
                                  Electrolysis Apparatus (electrolyzer). This
                                  breaks the bonds and creates your H2 and your
                                  O2. The H2 is fed into a storage system,
                                  typically energy intensive cryogenics are
                                  used, and then piped into the Fuel Cell.
                                  <br />
                                  <br />
                                  H-Bat on the other-hand, has atomised water
                                  passed into the system during the charge
                                  cycle. This is broken down using electricity
                                  and our proprietary catalysts, where the
                                  hydrogen is stored inside the device until
                                  needed.
                                  <br />
                                  <br />
                                  When electricity is required, the hydrogen
                                  migrates across the cells, combines with
                                  oxygen in the air. Once again generating
                                  water, and that much sought-after
                                  blue-hydrogen electricity!
                                </p>
                              </div>
                            </div>
                          </div>
                          <div className="col sqs-col-8 span-8">
                            <div className="row sqs-row">
                              <div className="col sqs-col-4 span-4">
                                <div
                                  className="sqs-block html-block sqs-block-html"
                                  data-block-type={2}
                                  id="block-e26da87d71611b17af2d"
                                >
                                  <div className="sqs-block-content">
                                    <h4
                                      style={{
                                        transitionTimingFunction: "ease",
                                        transitionDuration: "0.8s",
                                        transitionDelay: "0.371429s"
                                      }}
                                      className="preFade fadeIn"
                                    >
                                      Is this bad for the water cycle?
                                    </h4>
                                    <p
                                      className="sqsrte-small preFade fadeIn"
                                      style={{
                                        transitionTimingFunction: "ease",
                                        transitionDuration: "0.8s",
                                        transitionDelay: "0.385714s"
                                      }}
                                    >
                                      Our Hybrid Fuel Cell utilizes atomization
                                      technology to reduce the amount of water
                                      use per-charge as much as possible.
                                      <br />
                                      <br />
                                      The H-Bat eco-system offers a
                                      closed-looped energy cycle, without
                                      destroying or stressing precious water
                                      resources.
                                    </p>
                                    <p
                                      className="preFade fadeIn"
                                      data-rte-preserve-empty="true"
                                      style={{
                                        transitionTimingFunction: "ease",
                                        transitionDuration: "0.8s",
                                        transitionDelay: "0.4s"
                                      }}
                                    ></p>
                                    <h4
                                      style={{
                                        transitionTimingFunction: "ease",
                                        transitionDuration: "0.8s",
                                        transitionDelay: "0.414286s"
                                      }}
                                      className="preFade fadeIn"
                                    >
                                      How often does it need water?
                                    </h4>
                                    <p
                                      className="sqsrte-small preFade fadeIn"
                                      style={{
                                        transitionTimingFunction: "ease",
                                        transitionDuration: "0.8s",
                                        transitionDelay: "0.428571s"
                                      }}
                                    >
                                      This heavily depends on the size of the
                                      system. A typical 1kWh unit will consume
                                      60ml of water per charge cycle.
                                      <br />
                                      <br />
                                      Water recovery and Combined Heat and Power
                                      are both available for non-portable
                                      applications.
                                    </p>
                                  </div>
                                </div>
                              </div>
                              <div className="col sqs-col-4 span-4">
                                <div
                                  className="sqs-block html-block sqs-block-html"
                                  data-block-type={2}
                                  id="block-47af7b16c0ea656d4f03"
                                >
                                  <div className="sqs-block-content">
                                    <h4
                                      style={{
                                        transitionTimingFunction: "ease",
                                        transitionDuration: "0.8s",
                                        transitionDelay: "0.442857s"
                                      }}
                                      className="preFade fadeIn"
                                    >
                                      Is it safe?
                                    </h4>
                                    <p
                                      className="sqsrte-small preFade fadeIn"
                                      style={{
                                        transitionTimingFunction: "ease",
                                        transitionDuration: "0.8s",
                                        transitionDelay: "0.457143s"
                                      }}
                                    >
                                      H-Bat stores Hydrogen in a molecular lock.
                                      Not in gaseous or liquid forms. This
                                      means, our system is completely safe to
                                      use and operates at pressures of 1 - 3
                                      bar.
                                      <br />
                                      <br />
                                      Fire safety and prevention is our
                                      top-priority when working with Hydrogen.
                                      You can be assured, our systems are safe
                                      for your home.
                                    </p>
                                    <p
                                      className="sqsrte-small preFade fadeIn"
                                      data-rte-preserve-empty="true"
                                      style={{
                                        transitionTimingFunction: "ease",
                                        transitionDuration: "0.8s",
                                        transitionDelay: "0.471429s"
                                      }}
                                    ></p>
                                    <h4
                                      style={{
                                        transitionTimingFunction: "ease",
                                        transitionDuration: "0.8s",
                                        transitionDelay: "0.485714s"
                                      }}
                                      className="preFade fadeIn"
                                    >
                                      Does it generate heat?
                                    </h4>
                                    <p
                                      className="sqsrte-small preFade fadeIn"
                                      style={{
                                        transitionTimingFunction: "ease",
                                        transitionDuration: "0.8s",
                                        transitionDelay: "0.5s"
                                      }}
                                    >
                                      Yes, our system does generate it’s own
                                      heat. The breakdown of water into
                                      hydrogen, and the recombination of
                                      hydrogen with oxygen (to make water) are
                                      both exothermic.
                                      <br />
                                      <br />
                                      H-Bat generates roughly 100W of thermal
                                      energy for every 1kW of electrical energy
                                      produced by the device (during discharge).
                                      This heat is used for CHP, Combined Heat
                                      and Power. Perfect for any scale above
                                      5kW.
                                      <br />
                                      <br />
                                      For residential clients, this means you
                                      can passively heat your home directly from
                                      the battery (depending on size, usage, and
                                      thermal needs).
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
                </div>
              </div>
            </section>
            <section
              data-test="page-section"
              data-section-theme="black"
              className="page-section layout-engine-section background-width--full-bleed section-height--medium content-width--medium horizontal-alignment--center vertical-alignment--middle black"
              data-section-id="61b3cdb34d3bf66c062b27b6"
              data-controller="SectionWrapperController"
              data-current-styles='{ "backgroundImage": { "id": "61b3cff085ddcb60d01e1925", "recordType": 2, "addedOn": 1639174128163, "updatedOn": 1639174128243, "workflowState": 1, "publishOn": 1639174128163, "authorId": "617ab393b49a9d769760fc22", "systemDataId": "1632751734358-60WUFK7YEZ0GX82GW3CL", "systemDataVariants": "2880x2048,100w,300w,500w,750w,1000w,1500w,2500w", "systemDataSourceType": "PNG", "filename": "etvr_bg_dark.png", "mediaFocalPoint": { "x": 0.5, "y": 0.5, "source": 3 }, "colorData": { "topLeftAverage": "2d2c33", "topRightAverage": "494853", "bottomLeftAverage": "2d2c33", "bottomRightAverage": "494853", "centerAverage": "3b3a42", "suggestedBgColor": "2d2c33" }, "urlId": "oghco2ssi7m2cqr6mg9pcmdeipz0w6", "title": "", "body": null, "likeCount": 0, "commentCount": 0, "publicCommentCount": 0, "commentState": 2, "unsaved": false, "author": { "id": "617ab393b49a9d769760fc22", "displayName": "Zacariah Heim", "firstName": "Zacariah", "lastName": "Heim", "bio": "" }, "assetUrl": "https://images.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/1632751734358-60WUFK7YEZ0GX82GW3CL/etvr_bg_dark.png", "contentType": "image/png", "items": [ ], "pushedServices": { }, "pendingPushedServices": { }, "recordTypeLabel": "image", "originalSize": "2880x2048" }, "imageOverlayOpacity": 0.2, "backgroundWidth": "background-width--full-bleed", "sectionHeight": "section-height--medium", "customSectionHeight": 85, "horizontalAlignment": "horizontal-alignment--center", "verticalAlignment": "vertical-alignment--middle", "contentWidth": "content-width--medium", "sectionTheme": "black", "sectionAnimation": "none", "backgroundMode": "video" }'
              data-current-context='{ "video": { "playbackSpeed": 0.5, "filter": 1, "filterStrength": 0, "zoom": 0, "videoSourceProvider": "native", "nativeVideoContentItem": { "id": "61b3d4ac10fe2c16bbe2e8f1", "recordType": 61, "addedOn": 1639175340695, "updatedOn": 1639175340695, "authorId": "617ab393b49a9d769760fc22", "systemDataId": "6155bbd7-a8ea-4224-b238-5daf82d6f397", "systemDataVariants": "1920:1080,640:360", "systemDataSourceType": "mp4", "filename": "etvr_2.mp4", "body": null, "likeCount": 0, "commentCount": 0, "publicCommentCount": 0, "commentState": 1, "author": { "id": "617ab393b49a9d769760fc22", "displayName": "Zacariah Heim", "firstName": "Zacariah", "lastName": "Heim", "bio": "" }, "contentType": "video/mp4", "structuredContent": { "_type": "SqspHostedVideo", "videoCodec": "h264", "alexandriaUrl": "https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/6155bbd7-a8ea-4224-b238-5daf82d6f397/{variant}", "alexandriaLibraryId": "613f323315e7c403d0d6c265", "aspectRatio": 1.7777777777777777, "durationSeconds": 2.035367 }, "videoCodec": "h264", "alexandriaUrl": "https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/6155bbd7-a8ea-4224-b238-5daf82d6f397/{variant}", "alexandriaLibraryId": "613f323315e7c403d0d6c265", "aspectRatio": 1.7777777777777777, "durationSeconds": 2.035367, "items": [ ], "pushedServices": { }, "pendingPushedServices": { }, "recordTypeLabel": "sqsp-hosted-video", "originalSize": "1920:1080" } }, "backgroundImageId": null, "backgroundMediaEffect": null, "typeName": "page" }'
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
                    data-config-native-video='{ "id": "61b3d4ac10fe2c16bbe2e8f1", "recordType": 61, "addedOn": 1639175340695, "updatedOn": 1639175340695, "authorId": "617ab393b49a9d769760fc22", "systemDataId": "6155bbd7-a8ea-4224-b238-5daf82d6f397", "systemDataVariants": "1920:1080,640:360", "systemDataSourceType": "mp4", "filename": "etvr_2.mp4", "body": null, "likeCount": 0, "commentCount": 0, "publicCommentCount": 0, "commentState": 1, "author": { "id": "617ab393b49a9d769760fc22", "displayName": "Zacariah Heim", "firstName": "Zacariah", "lastName": "Heim", "bio": "" }, "contentType": "video/mp4", "structuredContent": { "_type": "SqspHostedVideo", "videoCodec": "h264", "alexandriaUrl": "https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/6155bbd7-a8ea-4224-b238-5daf82d6f397/{variant}", "alexandriaLibraryId": "613f323315e7c403d0d6c265", "aspectRatio": 1.7777777777777777, "durationSeconds": 2.035367 }, "videoCodec": "h264", "alexandriaUrl": "https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/6155bbd7-a8ea-4224-b238-5daf82d6f397/{variant}", "alexandriaLibraryId": "613f323315e7c403d0d6c265", "aspectRatio": 1.7777777777777777, "durationSeconds": 2.035367, "items": [ ], "pushedServices": { }, "pendingPushedServices": { }, "recordTypeLabel": "sqsp-hosted-video", "originalSize": "1920:1080" }'
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
                            loop
                            autoPlay
                            muted
                            playsInline
                            src="https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/6155bbd7-a8ea-4224-b238-5daf82d6f397/mp4-h264-1920:1080"
                          >
                            <source src="https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/6155bbd7-a8ea-4224-b238-5daf82d6f397/mp4-h264-1920:1080" />
                            <source src="https://video.squarespace-cdn.com/content/v1/613f323315e7c403d0d6c265/6155bbd7-a8ea-4224-b238-5daf82d6f397/mp4-h264-640:360" />
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
                    id="page-section-61b3cdb34d3bf66c062b27b6"
                  >
                    <div className="row sqs-row">
                      <div className="col sqs-col-12 span-12">
                        <div
                          className="sqs-block html-block sqs-block-html"
                          data-block-type={2}
                          id="block-5b51119782bb0cd7c01a"
                        >
                          <div className="sqs-block-content">
                            <h1
                              style={{
                                textAlign: "center",
                                transitionTimingFunction: "ease",
                                transitionDuration: "0.8s",
                                transitionDelay: "0.514286s"
                              }}
                              className="preSlide slideIn"
                            >
                              It all began with an idea.
                            </h1>
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
                                transitionDelay: "0.528571s"
                              }}
                            >
                              <h4
                                style={{
                                  textAlign: "center",
                                  transitionTimingFunction: "ease",
                                  transitionDuration: "0.8s",
                                  transitionDelay: "0.542857s"
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
                                    transitionDelay: "0.557143s"
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
                                    transitionDelay: "0.571429s"
                                  }}
                                >
                                  <h4
                                    style={{
                                      textAlign: "center",
                                      transitionTimingFunction: "ease",
                                      transitionDuration: "0.8s",
                                      transitionDelay: "0.585714s"
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
    </div>
  );
}
