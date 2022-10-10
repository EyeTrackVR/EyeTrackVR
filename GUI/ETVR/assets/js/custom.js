

// setTimeout(
// ()=>{
//     const container = document.querySelector('.user-items-list-carousel__slideshow-holder');
//     let scrollAmount = 0;
//     document.getElementById('slideRight').onclick = function () {
//       scrollAmount += 300
//       container.scrollTo({
//         top: 0,
//         left: scrollAmount,
//         behavior: 'smooth'
//       });
//     };
// }, 1000)

// setTimeout(
//   () => {
//     const container = document.querySelector('.user-items-list-carousel__slideshow-holder');
//     let scrollAmount = 0;
//     document.getElementById('mobileSlideRight').onclick = function () {
//       scrollAmount += 300
//       container.scrollTo({
//         top: 0,
//         left: scrollAmount,
//         behavior: 'smooth'
//       });
//     };
//   }, 1000)


// setTimeout(
//   () => {
//     const container = document.querySelector('.user-items-list-carousel__slideshow-holder');
//     let scrollAmount = 0;
//     document.getElementById('slideLeft').onclick = function () {
//       scrollAmount -= 300
//       container.scrollTo({
//         top: 0,
//         left: scrollAmount,
//         behavior: 'smooth'
//       });
//     };
//   }, 1000)


// setTimeout(
//   () => {
//     const container = document.querySelector('.user-items-list-carousel__slideshow-holder');
//     let scrollAmount = 0;

//     document.getElementById('mobileSlideLeft').onclick = function () {
//       console.log("LEFT called")

//       scrollAmount -= 300
//       container.scrollTo({
//         top: 0,
//         left: scrollAmount,
//         behavior: 'smooth'
//       });
//     };

//   }, 1000)

import { appWindow } from "@tauri-apps/api/window";

document
    .getElementById("titlebar-minimize")
    .addEventListener("click", () => appWindow.minimize());
document
    .getElementById("titlebar-maximize")
    .addEventListener("click", () => appWindow.toggleMaximize());
document
    .getElementById("titlebar-close")
    .addEventListener("click", () => appWindow.close());

