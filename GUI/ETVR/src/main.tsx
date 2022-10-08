import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../index.scss";
import App from "./App";
import reportWebVitals from "../assets/js/reportWebVitals";
import { invoke } from "@tauri-apps/api/tauri";

document.addEventListener("DOMContentLoaded", () => {
  // This will wait for the window to load, but you could
  // run this function on whatever trigger you want
  //sleep for 5 seconds to allow the window to load
  setTimeout(() => {
    invoke("close_splashscreen");
  }, 3000);
});

const root = createRoot(document.getElementById("root") as HTMLElement);

declare global {
  namespace JSX {
    interface IntrinsicElements {
      item: React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement>,
        HTMLElement
      >;
    }
  }
}
root.render(
  <StrictMode>
    <App />
  </StrictMode>
);

// If you want to start measuring performance in your app, pass a function
// to log results (for example: reportWebVitals(console.log))
// or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
reportWebVitals(console.log);
