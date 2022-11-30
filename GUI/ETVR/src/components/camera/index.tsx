import vector1 from '@assets/images/vector1.svg'
import { faGear } from '@fortawesome/free-solid-svg-icons'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { Menu } from '@headlessui/react'
import React from 'react'

interface ICameraProps {
  cameraType: boolean
  cameraAddress: string
}

interface ICameraDetails {
  cameraLabel: string
}

interface ICameraStatus {
  activeStatus: string
}

const ActiveStatus = (activeStatus: string) => {
  switch (activeStatus) {
    case 'active':
      return '#1FDD00'
    case 'loading':
      return '#F9AA33'
    default:
      return '#DD0000'
  }
}

const CameraStatusIndicator = (props: ICameraStatus) => {
  return (
    <>
      <svg
        className="flex items-center h-[30px] min-w-[30px] pl-2 rounded-[25px]"
        width="13"
        height="16"
        viewBox="0 0 13 16"
        fill="none"
        xmlns="http://www.w3.org/2000/svg">
        <rect width="13" height="13" rx="6.5" fill="#161616" />
        <g filter="url(#filter0_d_73_538)">
          <circle cx="6.5" cy="6.5" r="1.5" fill={`${ActiveStatus(props.activeStatus)}`} />
        </g>
        <defs>
          <filter
            id="filter0_d_73_538"
            x="1"
            y="5"
            width="11"
            height="11"
            filterUnits="userSpaceOnUse"
            color-interpolation-filters="sRGB">
            <feFlood flood-opacity="0" result="BackgroundImageFix" />
            <feColorMatrix
              in="SourceAlpha"
              type="matrix"
              values="0 0 0 0 0 
                      0 0 0 0 0 
                      0 0 0 0 0 
                      0 0 0 127 0"
              result="hardAlpha"
            />
            <feOffset dy="4" />
            <feGaussianBlur stdDeviation="2" />
            <feColorMatrix
              type="matrix"
              values="0 0 0 0 0.121333 0 0 0 0 0.866667 0 0 0 0 0 0 0 0 1 0"
            />
            <feBlend mode="normal" in2="BackgroundImageFix" result="effect1_dropShadow_73_538" />
            <feBlend
              mode="normal"
              in="SourceGraphic"
              in2="effect1_dropShadow_73_538"
              result="shape"
            />
          </filter>
        </defs>
      </svg>
    </>
  )
}

const CameraHeader = (props: ICameraDetails & ICameraStatus) => {
  return (
    <div className="flex flex-row justify-between">
      <CameraStatusIndicator activeStatus={props.activeStatus} />
      <span className="text-white"> {props.cameraLabel} </span>
      <div className="mr-2">
        <FontAwesomeIcon className="gear" icon={faGear} />
        <img className="" alt="" src={vector1} />
      </div>
    </div>
  )
}

const CameraDetails = (props: ICameraProps & ICameraStatus) => {
  return (
    <div className="flex justify-center leading-6 text-sm pt-2">
      <div className="grow-[100px]">
        <div className="flex justify-between">
          Camera address: <span className=""> {props.cameraAddress} </span>
        </div>
        <div className="flex justify-between">
          Camera type: <span className=""> {props.cameraType ? 'Wired' : 'Wireless'} </span>
        </div>
        <div className="flex justify-between">
          Status:
          <span className={`text-[${ActiveStatus(props.activeStatus)}]`}>{props.activeStatus}</span>
        </div>
      </div>
    </div>
  )
}

const CameraContainer = (props: ICameraProps & ICameraDetails & ICameraStatus) => {
  return (
    <div className="pb-[5rem] h-[100%] xl:pb-[1rem] grow flex-row pt-6 py-6 px-8">
      <Menu as="div" className="h-[100%]">
        <div className="h-[100%] flex-1 grow rounded-[20px] border-solid border border-black shadow-lg leading-5 font-sans font-medium">
          <div className="h-[100%] flex-1 overflow-auto grow rounded-[20px] pr-1 bg-[#0f0f0f] pt-[.5rem] pb-[.5rem] text-[#ffffffc4]">
            <CameraHeader cameraLabel={props.cameraLabel} activeStatus={props.activeStatus} />
            <CameraDetails
              activeStatus={props.activeStatus}
              cameraType={props.cameraType}
              cameraAddress={props.cameraAddress}
            />
          </div>
        </div>
      </Menu>
    </div>
  )
}

export default CameraContainer
