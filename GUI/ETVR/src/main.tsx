import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../index.scss";
import App from "./App";
import reportWebVitals from "../assets/js/reportWebVitals";
import { invoke } from "@tauri-apps/api/tauri";
import username from "../src-tauri/config/config.json";

/**
 * @description This is the entry point of the application.
 * We check the config file, and if it is empty we grab the username from windows.
 * If it is not empty we continue.
 *
 */
document.addEventListener("DOMContentLoaded", () => {

  if (!username.name) {
    invoke("get_user").then((username) => {
      console.log(username);
    });
  }

  //* This will wait for the window to load, but we could
  //* run this function on whatever trigger we want
  //* sleep for 3 seconds to allow the window to load
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
