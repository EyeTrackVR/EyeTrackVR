import { Outlet } from "react-router-dom";
import AppRoutes from "./routes/app/Routes";

export default function App() {
    return (
        <main className="App">
            <AppRoutes />
            <Outlet />
        </main>
    );
}
