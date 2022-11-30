import React, { useState } from 'react'

interface SliderProps {
  min: number
  max: number
  step: number
  value: number
  id: string
}

export default function Slider(props: SliderProps) {
  const [range, setValue] = useState({
    value: props.value,
  })

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setValue({ value: parseInt(e.target.value) })
  }

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
  )
}
