import { useState } from "react";
export default function Slider(props) {
    const [range, setValue] = useState({
        value: props.value,
    });

    const handleChange = (e) => {
        setValue({ value: e.target.value });
    };

    return (
        <div className="">
            <input
                type="range"
                min={props.min}
                max={props.max}
                value={range.value}
                className=""
                id={props.id}
                step={props.step}
                onChange={handleChange}
            />
        </div>
    );
}
