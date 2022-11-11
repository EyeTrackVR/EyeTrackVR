import Input from "@components/Settings/Inputs";
import Tooltip from "@components/Tooltip";
import { faChevronDown } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useEffect, useRef } from "react";
import { DropDataData } from "../DropDownData";

export default function DropDown(props) {
    const ref = useRef<HTMLDivElement>(null);
    const { onClickOutside } = props;
    useEffect(() => {
        const handleClickOutside = (event) => {
            if (ref.current && !ref.current.contains(event.target)) {
                onClickOutside && onClickOutside();
            }
        };
        document.addEventListener("click", handleClickOutside, true);
        return () => {
            document.removeEventListener("click", handleClickOutside, true);
        };
    }, [onClickOutside]);
    return (
        <div
            className={
                props.showSettings
                    ? `flex-col xxs:invisible xxs:hidden`
                    : `flex-col xxs:invisible xxs:hidden`
            }
        >
            <div className="h-[55%] content-center">
                <div className="flex flex-row rounded-[14px] justify-start border-none inset shadow-lg content-center leading-5pl-[1rem] font-sans font-medium text-[.75rem]rounded-[15px] h-[100%] bg-[#0e0e0e] text-[#5f5f5f]">
                    <div className="flex rounded-[14px] h-[100%] bg-[#0e0e0e] flex-row basis-[100%] justify-center content-stretch pt-[8px] pb-[8px] pr-[8px]">
                        <span className="text-[#5f5f5f] pl-[1rem]">
                            {props.name}
                        </span>
                    </div>
                    <FontAwesomeIcon
                        onClick={() => props.onClose()}
                        className="object-cover mt-[3px] pt-[8px] pl-[2rem] pr-[1rem] text-[#f5f5f5]"
                        icon={faChevronDown}
                    />
                </div>
            </div>
            <div
                ref={ref}
                className={
                    props.showSettings
                        ? `flex flex-col flex-grow h-[55%] content-center mt-[5px] z-10 bg-gray-800 rounded-lg shadow-lg`
                        : `hidden`
                }
            >
                <div className="flex flex-grow content-start rounded-[14px] border-none shadow-lg leading-5 font-sans font-medium text-[.75rem] h-[100%] bg-[#0e0e0e] text-[#5f5f5f]">
                    <div className="rounded-[14px] h-[100%] bg-[#0e0e0e] pt-[.5rem] pb-[.5rem] text-[#5f5f5f]">
                        <ul>
                            {DropDataData.map((item, index) => (
                                <li
                                    key={index}
                                    className="flex items-center justify-center content-center"
                                >
                                    <div className="flex flex-grow items-center justify-center content-center rounded-[8px] pt-[.2rem] pb-[.2rem] pl-[1rem] pr-[1rem] ml-[4px] hover:bg-[#252536]">
                                        <span className="">
                                            <label
                                                htmlFor=""
                                                className="flex content-center items-center"
                                            >
                                                <Tooltip tooltip={item.name}>
                                                    <span className="">
                                                        {item.icon}
                                                    </span>
                                                </Tooltip>
                                                <input
                                                    className="ml-[100px] align-middle rounded bg-[#0e0e0e] text-[#5f5f5f] text-sm font-sans font-medium text-[.75rem] focus:outline-none focus:ring-0 focus:border-0"
                                                    type="checkbox"
                                                    id={item.id}
                                                />
                                            </label>
                                        </span>
                                    </div>
                                </li>
                            ))}
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    );
}

/* 

*/
