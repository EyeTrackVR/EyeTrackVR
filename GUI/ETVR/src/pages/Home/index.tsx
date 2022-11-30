import CameraContainer from '@components/camera'

const Main = () => {
  return (
    <div>
      <CameraContainer 
        activeStatus={true}
        cameraType={true}
        cameraAddress="192.168.0.204"
        cameraLabel="Left Eye"
      />
    </div>
  )
}

export default Main
