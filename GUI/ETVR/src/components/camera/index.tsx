import vector1 from '@assets/images/vector1.svg'
import { CameraStatusIndicator, ActiveStatus } from '@components/CameraStatus'
import { faGear } from '@fortawesome/free-solid-svg-icons'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { Menu } from '@headlessui/react'
import React from 'react'
import type { ICameraStatus } from '@components/CameraStatus'

interface ICameraProps {
  cameraType: boolean
  cameraAddress: string
}

interface ICameraDetails {
  cameraLabel: string
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
