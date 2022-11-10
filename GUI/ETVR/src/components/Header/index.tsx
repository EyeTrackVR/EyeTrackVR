import logo from "/images/logo.png";
import { faGear } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import Settings from "@pages/Settings";
import { useState } from "react";
import Modal from "@components/Modal";

export default function Header(props) {
    const [showSettings, setShowSettings] = useState(false);
    return (
        <>
            <header
                className="container px-4 py-2 flex items-center justify-between mx-auto"
                style={{
                    paddingTop: "20px",
                }}
            >
                <div className="navbar">
                    <div className="menu-bars">
                        <button
                            onClick={() => setShowSettings(!showSettings)}
                            className="settings-button ml-4 p-1 hover:bg-gray-200 border rounded-full py-3 px-4 mr-5 focus:bg-gray-100 transition duration-200 ease-in focus:shadow-inner"
                        >
                            <FontAwesomeIcon icon={faGear} />
                        </button>
                    </div>
                </div>
                <h2 className="ml-4 text-xl text-gray-500 font-bold">
                    <span className="text-gray-900">ESP32</span> Data Logger
                </h2>
                <div className="flex h-[55%] flex-row basis-[18%] justify-start content-center mt-[5px]">
                    <select className="rounded h-[100%] bg-[#0e0e0e] text-[#5f5f5f]">
                        <option className="">
                            <h1 className="ml-4 text-xl text-gray-500 fond-bold">
                                <span className="text-gray-900">Welcome</span>{" "}
                                {props.name}
                            </h1>
                        </option>
                    </select>
                </div>
            </header>
            <div className="nav-menu z-10">
                <Modal
                    isVisible={showSettings}
                    onClose={() => setShowSettings(false)}
                    width="200"
                >
                    <Settings />
                </Modal>
            </div>
        </>
    );
}
