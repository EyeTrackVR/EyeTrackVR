import etvrLogo from "/images/logo.png";
import {
    faCamera,
    faChevronDown,
    faGear,
} from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import Settings from "@pages/Settings";
import { useState } from "react";
import Modal from "@components/Modal";

export default function Header(props) {
    const [showSettings, setShowSettings] = useState(false);
    return (
        <>
            <header
                style={{
                    paddingTop: "20px",
                }}
            >
                <div className="flex justify-around items-center">
                    <div className="flex-none">
                        <img
                            onClick={() => setShowSettings(!showSettings)}
                            src={etvrLogo}
                            alt="eytrackvrlogo"
                            className="bg-gray-800
                                            hover:bg-gray-900 
                                            rounded-full
                                          focus:bg-gray-900 
                                            transition 
                                            duration-200 
                                            ease-in
                                            focus:shadow-inner 
                                            w-[90px] shadow-lg"
                        />
                    </div>
                    <div
                        className="flex
                                   h-[55%]
                                   content-center 
                                   items-center 
                                   mt-[5px]"
                    >
                        <div
                            className="flex
                                       flex-grow
                                       justify-center
                                       border-none
                                       shadow-lg
                                       content-center 
                                       leading-5 
                                       font-sans 
                                       font-medium 
                                       text-[.75rem]
                                       rounded-[15px] 
                                       h-[100%]
                                       w-[100%]
                                       bg-[#0e0e0e] 
                                       text-[#5f5f5f]"
                        >
                            <div
                                className="flex
                                           flex-grow 
                                           content-center
                                           justify-evenly
                                           h-[100%]
                                           leading-5 
                                           font-sans 
                                           font-medium 
                                           rounded-[14px]
                                           p-[5px]
                                           bg-[#0e0e0e]"
                            >
                                <div className="ml-[1.25rem] rounded-[8px] pt-[.2rem] pb-[.2rem] pl-[1.25rem] pr-[1.25rem] hover:bg-[#252536]">
                                    <FontAwesomeIcon
                                        size="xl"
                                        icon={faCamera}
                                    />
                                </div>
                                <div className="ml-[1.25rem] mr-[1.25rem] rounded-[8px] pt-[.2rem] pb-[.2rem] pl-[1.25rem] pr-[1.25rem] hover:bg-[#252536]">
                                    <FontAwesomeIcon size="xl" icon={faGear} />
                                </div>
                            </div>
                        </div>
                    </div>
                    <div
                        className="flex 
                                   h-[55%] 
                                   content-center 
                                   mt-[5px]"
                    >
                        <div
                            className="flex 
                                       flex-row 
                                       justify-start 
                                       border-none 
                                       inset 
                                       shadow-lg 
                                       content-center 
                                       leading-5
                                       pl-[1rem] 
                                       font-sans 
                                       font-medium 
                                       text-[.75rem]
                                       rounded-[15px] 
                                       h-[100%] 
                                       bg-[#0e0e0e] 
                                       text-[#5f5f5f]"
                        >
                            <div
                                className="flex 
                                           rounded-[14px] 
                                           h-[100%] 
                                           bg-[#0e0e0e] 
                                           flex-row 
                                           basis-[100%] 
                                           justify-center 
                                           content-stretch 
                                           pt-[8px] 
                                           pb-[8px] 
                                           pr-[8px]"
                            >
                                <span className="text-[#5f5f5f]">
                                    {props.name}
                                </span>
                            </div>
                            <FontAwesomeIcon
                                className="object-cover 
                                           mt-[3px] 
                                           pt-[8px] 
                                           pl-[2rem] 
                                           pr-[1rem] 
                                           text-[#f5f5f5]"
                                icon={faChevronDown}
                            />
                        </div>
                    </div>
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
