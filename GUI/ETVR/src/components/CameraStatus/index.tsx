// NOTE: https://fecolormatrix.com/

/* eslint-disable no-multi-str */
export interface ICameraStatus {
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

const GenerateMatrixShadow = (activeStatus: string) => {
  switch (activeStatus) {
    case 'active':
      return '0 0 0 0 0.121333 \
              0 0 0 0 0.866667 \
              0 0 0 0 0 \
              0 0 0 1 0'
    case 'loading':
      return '0 0 0 0 1 \
              0 0 0 0 0.20166699999999999 \
              0 0 0 0 -1.878667 \
              0 0 0 1 0'
    default:
      return '0 0 0 0 1.966667 \
              0 0 0 0 0 \
              0 0 0 0 -0.04366700000000001 \
              0 0 0 1 0'
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
            <feColorMatrix type="matrix" values={`${GenerateMatrixShadow(props.activeStatus)}`} />
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

export { CameraStatusIndicator, ActiveStatus, GenerateMatrixShadow }
