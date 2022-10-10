import * as React from "react";
import username from "../../../src-tauri/config.json";

export function Greeting() {
  const [name, setName] = React.useState("");

  React.useEffect(() => {
    setName(username.name);
  }, []);
  return (
    <>
      <div className="username-div">
        <p className="username-content">
          {name ? `Welcome ${name}` : "Welcome"}
        </p>
      </div>
    </>
  );
}
