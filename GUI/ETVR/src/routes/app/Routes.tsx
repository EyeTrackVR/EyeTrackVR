import Header from "@components/Header";
import { SettingsPage } from "@components/Settings";
import { Main } from "@pages/Home";
import { useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import config from "../../../src-tauri/config/config.json";

// TODO: Add autodetection component that chooses between the one eye and two eye modes based on the number of cameras connected
// TODO: Implement a settings page that allows the user to change the settings of the application

export default function AppRoutes() {
    const [name, setName] = useState("");

    useEffect(() => {
        setName(config["name"]);
    }, []);
    return (
        <BrowserRouter>
            <Header name={name ? "Welcome " + name : "!"} />
            <Routes>
                <Route path="/" element={<Main />} />
                <Route path="/settings" element={<SettingsPage />} />
            </Routes>
        </BrowserRouter>
    );
}
