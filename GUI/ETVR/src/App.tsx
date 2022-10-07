import AppRoutes from "./routes/frontend/Routes"
import { Outlet } from "react-router-dom";

function App() {
  const date = '__DATE__'
  return (
    <main className="App">
      <AppRoutes />
      <Outlet />
    </main>
  );
}

export default App