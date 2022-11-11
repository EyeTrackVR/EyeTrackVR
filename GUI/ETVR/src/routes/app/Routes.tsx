import Header from "@components/Header";
import { Settings } from "@components/Settings";
import { Main } from "@pages/Home";
import { useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import config from "../../../src-tauri/config/config.json";

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
                <Route path="/settings" element={<Settings />} />
            </Routes>
        </BrowserRouter>
    );
}
