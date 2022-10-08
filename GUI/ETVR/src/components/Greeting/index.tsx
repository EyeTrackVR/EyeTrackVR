import * as React from "react";
import UserInterface from "@interfaces/Helpers/userinterface";
import { invoke } from "@tauri-apps/api";
import { listen } from "@tauri-apps/api/event";

export function Greeting() {
  const [user, setUser] = React.useState(null);
  return (
    <div>
      <header className="App-header">
        <p>{user ? `Hello ${user}` : "Hello, stranger"}</p>
        <pre>
          <>{user}</>
        </pre>
      </header>
    </div>
  );
}
