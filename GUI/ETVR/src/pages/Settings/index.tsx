//import { Button } from "@src/components/Buttons";
import { Button } from '@components/Buttons'
import Slider from '@components/Slider'
import Tooltip from '@components/Tooltip'
import { Menu, Switch } from '@headlessui/react'
import { GeneralSettings, AlgoSettings } from '@src/static/SettingsStates'
import { useMDNSScanner } from '@src/utils/hooks/useMDNSScanner'
import { useRestClient } from '@src/utils/hooks/useRestClient'

//import LocalStorageHandler from '@src/utils/Helpers/localStorageHandler'
import { useState } from 'react'

export function SettingsPage() {
  const [enabled, setEnabled] = useState(false)
  const { scan } = useMDNSScanner('_waterchamber._tcp', 10)
  const { request } = useRestClient(
    '/api/v1/builtin/command/json?type=data',
    'waterchamber.local',
    'GET'
  )
  return (
    <div className="py-4 px-8">
      <Menu as="div" className="h-[85%] content-center">
        <div className="flex flex-grow content-start rounded-[14px] border-solid border border-black shadow-lg leading-5 font-sans font-medium text-[.75rem] h-[100%]">
          <div className="overflow-auto flex-grow rounded-[14px] h-[100%] pr-1 bg-[#0f0f0f] pt-[.5rem] pb-[.5rem] text-[#ffffffc4]">
            <div className="flex flex-col divide-y divide-gray-800">
              <span className="pb-1">General Settings</span>
              <div className="pt-1 pb-2 ml-32 mr-32 drop-shadow-lg" />
            </div>
            <div className="flex-grow flex-col justify-start">
              <ul>
                <li>
                  <div className="pl-[1rem]">
                    <Button
                      text="Test MDNS Scan"
                      color="#6f4ca1"
                      onClick={scan}
                      shadow="0 10px 20px -10px rgba(24, 90, 219, 0.6)"
                    />
                  </div>
                  <div className="pl-[1rem]">
                    <Button
                      text="Test REST Client"
                      color="#6f4ca1"
                      onClick={request}
                      shadow="0 10px 20px -10px rgba(24, 90, 219, 0.6)"
                    />
                  </div>
                </li>
                {GeneralSettings.map((item, index) => (
                  <li key={index}>
                    <div className="pl-[1rem] flex justify-start">
                      <Switch.Group>
                        <Switch.Label>
                          <div className="flex flex-row flex-grow items-center content-center justify-between rounded-[8px] pt-[.2rem] pb-[.2rem] pl-[1rem] pr-[1rem] ml-[4px] hover:bg-[#2525369d]">
                            <div className="pr-4 pt-[.2rem]">
                              <Switch
                                name={item.name}
                                checked={enabled}
                                onChange={setEnabled}
                                className="relative inline-flex h-4 w-8 items-center rounded-full ui-checked:bg-violet-800 ui-checked:text-white ui-not-checked:bg-[#2a2929] ui-not-checked:text-[#5f5f5f]">
                                <span
                                  className={`${
                                    enabled ? 'translate-x-5' : 'translate-x-0'
                                  } inline-block h-4 w-4 rounded-full bg-white transform transition ease-in-out duration-200`}
                                />
                              </Switch>
                            </div>
                            <Tooltip tooltip={item.tooltip}>
                              <span>Test</span>
                            </Tooltip>
                          </div>
                        </Switch.Label>
                      </Switch.Group>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
            <div className="flex flex-col divide-y divide-gray-800">
              <span className="pb-1">Tracking Algorithm Settings</span>
              <div className="pt-1 pb-2 ml-32 mr-32 drop-shadow-lg" />
            </div>
            <div className="flex-grow flex-col justify-start">
              <ul>
                {AlgoSettings.map((item, index) => (
                  <li key={index}>
                    <div className="pl-[1rem] flex justify-start">
                      <div className="flex flex-row items-center content-center justify-start rounded-[8px] pt-[.2rem] pb-[.2rem] pl-[1rem] pr-[1rem] ml-[4px] hover:bg-[#2525369d]">
                        <Tooltip tooltip={item.tooltip}>
                          <div className="pr-4 pt-[.2rem]">
                            <Slider
                              id={item.id}
                              min={item.min}
                              max={item.max}
                              value={item.value}
                              step={item.step}
                              className=""
                            />
                          </div>
                          <span> {item.name} </span>
                        </Tooltip>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </Menu>
    </div>
  )
}

/* <Button
    text="Log"
    color="#6f4ca1"
    onClick={() => console.log("clicked")}
    shadow="0 10px 20px -10px rgba(24, 90, 219, 0.6)"
/> */
