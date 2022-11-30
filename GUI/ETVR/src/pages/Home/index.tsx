import CameraContainer from '@components/camera'

//! temporary just for debugging and testing
const CameraStatus = Object.freeze({
  active: 'active',
  loading: 'loading',
  inactive: 'inactive',
})

const Main = () => {
  return (
    <div>
      <CameraContainer
        activeStatus={CameraStatus.inactive}
        cameraType={true}
        cameraAddress="192.168.0.204"
        cameraLabel="Left Eye"
      />
    </div>
  )
}

export default Main
