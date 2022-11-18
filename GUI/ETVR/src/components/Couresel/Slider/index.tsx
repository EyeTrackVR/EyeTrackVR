import { useEffect } from "react";

export default function Slider({ setSliderLength, children }) {
    useEffect(() => {
        setSliderLength(children?.length);
    });

    return (
        <div className="h-full w-full relative overflow-hidden">
            {children.map((element) => element)}
        </div>
    );
}
