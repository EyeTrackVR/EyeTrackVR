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
                    <div className="flex">
                        <div className="">
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
                    </div>
                    <div
                        className="flex 
                                   h-[55%] 
                                   basis-[18%] 
                                   justify-center 
                                   content-center 
                                   items-center 
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
                                       font-sans 
                                       font-medium 
                                       text-[.75rem] 
                                       pl-[14px] 
                                       mr-[-182px] 
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
                                           justify-around 
                                           content-stretch 
                                           pt-[8px] 
                                           pb-[8px] 
                                           pr-[8px]"
                            >
                                <div
                                    className="flex 
                                                flex-row 
                                                xl:space-x-24 
                                                h-[100%] 
                                                content-center 
                                                leading-5 
                                                font-sans 
                                                font-medium text-[.75rem] 
                                                justify-around 
                                                basis-[100%]"
                                >
                                    <div className="pr-[6px]">
                                        <FontAwesomeIcon
                                            className="ml-8"
                                            icon={faCamera}
                                        />
                                    </div>
                                    <div className="pl-[6px]">
                                        <FontAwesomeIcon
                                            className="mr-8"
                                            icon={faGear}
                                        />
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div
                        className="flex 
                                    h-[55%] 
                                    basis-[18%] 
                                    justify-around 
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
                                       font-sans 
                                       font-medium 
                                       text-[.75rem] 
                                       pl-[14px] 
                                       mr-[-182px] 
                                       rounded-[15px] h-[100%] 
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
                                           justify-around 
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
