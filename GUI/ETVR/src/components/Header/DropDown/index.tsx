import { faChevronDown } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useEffect, useRef } from "react";

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
        <div className="flex-col mt-[2.5rem] xxs:invisible xxs:hidden">
            <div className="h-[55%] content-center mt-[5px]">
                <div className="flex flex-row rounded-[14px] justify-start border-none inset shadow-lg content-center leading-5pl-[1rem] font-sans font-medium text-[.75rem]rounded-[15px] h-[100%] bg-[#0e0e0e] text-[#5f5f5f]">
                    <div className="flex rounded-[14px] h-[100%] bg-[#0e0e0e] flex-row basis-[100%] justify-center content-stretch pt-[8px] pb-[8px] pr-[8px]">
                        <span className="text-[#5f5f5f] pl-[1rem]">
                            {props.name}
                        </span>
                    </div>
                    <FontAwesomeIcon
                        onClick={props.setShowSettings}
                        className="object-cover mt-[3px] pt-[8px] pl-[2rem] pr-[1rem] text-[#f5f5f5]"
                        icon={faChevronDown}
                    />
                </div>
            </div>
            <div
                className={
                    props.showSettings
                        ? `h-[55%] content-center mt-[5px]`
                        : `h-[55%] content-center mt-[5px] invisible`
                }
            >
                <div
                    ref={ref}
                    className="flex flex-row rounded-[14px] justify-start border-none inset shadow-lg content-center leading-5pl-[1rem] font-sans font-medium text-[.75rem]rounded-[15px] h-[100%] bg-[#0e0e0e] text-[#5f5f5f]"
                >
                    <div className="flex rounded-[14px] h-[100%] bg-[#0e0e0e] flex-row basis-[100%] justify-center content-stretch pt-[8px] pb-[8px] pr-[8px]">
                        <span className="text-[#5f5f5f] pl-[1rem]">
                            {props.name}
                        </span>
                    </div>
                </div>
            </div>
        </div>
    );
}
