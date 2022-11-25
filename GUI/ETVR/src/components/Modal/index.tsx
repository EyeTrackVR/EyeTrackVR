import type { ReactNode } from 'react'

interface IModalProps {
  children: ReactNode
  isVisible: boolean
  width?: string
  onClose: () => void
}

export const Modal = ({ children, isVisible, width, onClose }: IModalProps): JSX.Element | null => {
  if (!isVisible) return null
  return (
    <div
      id="wrapper"
      onClick={(e) => {
        const id = (e.target as HTMLInputElement).id
        if (id.match('wrapper')) onClose()
      }}
      className="fixed pt-8 mt-7 inset-0 bg-black bg-opacity-25 backdrop-blur-xl flex justify-center items-center content-center self-center">
      <div
        className={`md:w-[${width}px] h-[100%] xl:mt-[65px] lg:mt-[65px] sm:mt-[55px] xs:mt-[55px] md:mt-[45px] 2xl:mt-[95px] flex flex-col pb-32`}>
        <div className="px-1 flex items-center justify-center w-[99.50%] h-[25px]">
          <button
            type="button"
            className="ml-auto place-self-end text-gray-900 rounded-lg focus:ring-2 focus:ring-gray-400 p-1 hover:bg-gray-200 inline-flex h-6 w-6 dark:bg-gray-300 dark:text-gray-600 dark:hover:bg-gray-400"
            aria-label="Close"
            onClick={() => onClose()}>
            <span className="sr-only">Close</span>
            <svg
              aria-hidden="true"
              className="w-4 h-4"
              fill="currentColor"
              viewBox="0 0 20 20"
              xmlns="http://www.w3.org/2000/svg">
              <path
                fillRule="evenodd"
                d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        </div>
        <div className="bg-none p-2 rounded h-[100%] 2xl:h-[100%] md:h-[110%]">{children}</div>
      </div>
    </div>
  )
}
