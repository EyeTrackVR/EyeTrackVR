//import { Button } from "@src/components/Buttons";
import LocalStorageHandler from "@components/Helpers/localStorageHandler";
import Tooltip from "@components/Tooltip";
import { faChevronDown } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { Menu, Transition, Switch } from "@headlessui/react";
import { useEffect, useRef, useState, Fragment } from "react";

export function Settings() {
    return (
        <div className="py-4 px-8">
            <div className="flex flex-grow content-start rounded-[14px] border-solid border border-black shadow-lg leading-5 font-sans font-medium text-[.75rem] h-[100%]">
                <div className="flex-grow rounded-[14px] h-[100%] pr-1 bg-[#0f0f0f] pt-[.5rem] pb-[.5rem] text-[#ffffffc4]">
                    <div className="flex flex-row pl-72">
                        <span className="pl-[1rem]">General Settings</span>
                    </div>
                    <div className="content-start grid grid-flow-row auto-rows-max pr-9">
                        <div>01</div>
                        <div>02</div>
                        <div>03</div>
                    </div>
                </div>
            </div>
        </div>
    );
}

/* <Button
    text="Log"
    color="#6f4ca1"
    onClick={() => console.log("clicked")}
    shadow="0 10px 20px -10px rgba(24, 90, 219, 0.6)"
/> */
