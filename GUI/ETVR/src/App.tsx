//import AppRoutes from "./routes/frontend/Routes";
//import { Outlet } from "react-router-dom";
import MainWindow from "@pages/ETVRPage01";
/* import { appWindow } from "@tauri-apps/api/window";
await appWindow.setDecorations(false); */

function App() {
  return (
    
    <main className="App">
      <MainWindow />
      {/* <Outlet /> */}
    </main>
  );
}

export default App;
