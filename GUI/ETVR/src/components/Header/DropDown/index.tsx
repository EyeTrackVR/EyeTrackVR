import Tooltip from '@components/Tooltip'
import { faChevronDown } from '@fortawesome/free-solid-svg-icons'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { Menu, Transition, Switch } from '@headlessui/react'
import { Settings } from '@src/static/SettingsStates'
import { DropDataData } from '@static/defaultData/index'
import LocalStorageHandler from '@utils/Helpers/localStorageHandler'
import { useEffect, useRef, useState, Fragment } from 'react'

export interface Iprops {
  name: string
  showSettings: boolean
  onClose: () => void
  onClickOutside: () => void
}

export default function DropDown({ name, showSettings, onClose, onClickOutside }: Iprops) {
  const [enabled, setEnabled] = useState({
    blob: false,
  })
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent): void => {
      if (event.target instanceof HTMLElement && !ref.current?.contains(event.target)) {
        onClickOutside()
      }
    }
    document.addEventListener('click', handleClickOutside, true)
    return () => {
      document.removeEventListener('click', handleClickOutside, true)
    }
  }, [onClickOutside])

  const handleChange = (e: boolean, id: string) => {
    setEnabled({ ...enabled, [id]: e })
    Settings[0][id] = e
    LocalStorageHandler(id, e)
  }

  return (
    <div
      className={
        showSettings ? `flex-col xxs:invisible xxs:hidden` : `flex-col xxs:invisible xxs:hidden`
      }>
      <Menu ref={ref} as="div" className="h-[55%] content-center">
        <div className="flex flex-row rounded-[14px] justify-start border-none inset shadow-lg content-center leading-5pl-[1rem] font-sans font-medium text-[.75rem]rounded-[15px] h-[100%] bg-[#0e0e0e] text-[#5f5f5f]">
          <Menu.Button className="inline-flex w-full justify-center rounded-[14px] bg-[#0e0e0e] bg-opacity-20 text-sm font-medium hover:bg-opacity-30 focus:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-opacity-75">
            <div className="flex rounded-[14px] h-[100%] bg-[#0e0e0e] flex-row basis-[100%] justify-center content-stretch pt-[8px] pb-[8px] pr-[8px]">
              <span className="text-[#5f5f5f] pl-[1rem]">{name}</span>
            </div>
            <FontAwesomeIcon
              onClick={onClose}
              className="text-violet-200 hover:text-violet-400 object-cover mt-[3px] pt-[8px] pl-[2rem] pr-[1rem]"
              icon={faChevronDown}
            />
          </Menu.Button>
        </div>
        <Transition
          as={Fragment}
          enter="transition ease-out duration-100"
          enterFrom="transform opacity-0 scale-95"
          enterTo="transform opacity-100 scale-100"
          leave="transition ease-in duration-75"
          leaveFrom="transform opacity-100 scale-100"
          leaveTo="transform opacity-0 scale-95">
          <Menu.Items className="absolute z-10 w-[182.13px]">
            <div className="py-1">
              <div className="flex flex-grow content-start rounded-[14px] border-none shadow-lg leading-5 font-sans font-medium text-[.75rem] h-[100%] bg-[#0e0e0e] text-[#5f5f5f]">
                <div className="flex-grow rounded-[14px] h-[100%] pr-1 bg-[#0e0e0e] pt-[.5rem] pb-[.5rem] text-[#5f5f5f]">
                  <ul>
                    {DropDataData.map((item, index) => (
                      <li
                        key={index}
                        className="flex-grow justify-between items-center content-center">
                        <Menu.Item>
                          {() => (
                            <>
                              <Switch.Group>
                                <Switch.Label>
                                  <div className="flex flex-row flex-grow items-center content-center justify-between rounded-[8px] pt-[.2rem] pb-[.2rem] pl-[1rem] pr-[1rem] ml-[4px] hover:bg-[#2525369d]">
                                    <Tooltip tooltip={item.name}>
                                      <span>{item.icon}</span>
                                    </Tooltip>
                                    <div className="pl-4 pt-[.2rem]">
                                      <Switch
                                        key={item.id}
                                        name={item.id}
                                        checked={enabled[item.id]}
                                        onChange={(e) => handleChange(e, item.id)}
                                        className="relative inline-flex h-4 w-8 items-center rounded-full ui-checked:bg-violet-800 ui-checked:text-white ui-not-checked:bg-[#2a2929] ui-not-checked:text-[#5f5f5f]">
                                        <span
                                          className={`${
                                            enabled[item.id] ? 'translate-x-5' : 'translate-x-0'
                                          } inline-block h-4 w-4 rounded-full bg-white transform transition ease-in-out duration-200`}
                                        />
                                      </Switch>
                                    </div>
                                  </div>
                                </Switch.Label>
                              </Switch.Group>
                            </>
                          )}
                        </Menu.Item>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          </Menu.Items>
        </Transition>
      </Menu>
    </div>
  )
}
