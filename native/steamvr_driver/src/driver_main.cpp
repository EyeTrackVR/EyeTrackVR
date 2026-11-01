// EyeTrackVR SteamVR driver: feeds EyeTrackVR's gaze into SteamVR's eye tracking input on
// whatever headset is in use, so SteamVR's OpenXR runtime offers XR_EXT_eye_gaze_interaction
// and OpenVR apps see Prop_SupportsXrEyeGazeInteraction_Bool (e.g. PimaxMagic4All).
//
// No devices of its own. It attaches an /eyetracking component to the HMD, either directly
// (HMD already registered when this driver loads) or by wrapping the HMD as its driver adds it.

#include <atomic>
#include <cmath>
#include <cstring>
#include <mutex>

#include <openvr_driver.h>

#include "gaze_source.h"
#include "hmd_shim.h"
#include "log.h"

#if defined(_WIN32)
#define ETVR_EXPORT extern "C" __declspec(dllexport)
#else
#define ETVR_EXPORT extern "C" __attribute__((visibility("default")))
#endif

namespace etvr {

    namespace {
        constexpr const char* kEyeTrackingPath = "/eyetracking";
        constexpr int64_t kPropertyCheckIntervalNs = 1'000'000'000;
        // Fixation point distance along the gaze ray. SteamVR builds the gaze pose from
        // origin -> target, so only the direction matters.
        constexpr float kTargetDistanceM = 1.0f;

        const char* inputErrorName(vr::EVRInputError error) {
            switch (error) {
            case vr::VRInputError_None:
                return "None";
            case vr::VRInputError_NameNotFound:
                return "NameNotFound";
            case vr::VRInputError_WrongType:
                return "WrongType";
            case vr::VRInputError_InvalidHandle:
                return "InvalidHandle";
            case vr::VRInputError_InvalidParam:
                return "InvalidParam";
            case vr::VRInputError_PermissionDenied:
                return "PermissionDenied";
            default:
                return "other";
            }
        }
    } // namespace

    class EyeTrackVRProvider final : public vr::IServerTrackedDeviceProvider {
      public:
        vr::EVRInitError Init(vr::IVRDriverContext* pDriverContext) override {
            VR_INIT_SERVER_DRIVER_CONTEXT(pDriverContext);
            Log("EyeTrackVR gaze driver starting");

            const bool hooked = shim::install(
                vr::VRServerDriverHost(),
                [this](uint32_t index) { attach(index, "shim"); },
                [this]() { detach(); });
            Log(hooked ? "Watching for the HMD" : "HMD shim unavailable; relying on direct attach");

            // The headset's driver may have loaded first.
            tryDirectAttach();
            return vr::VRInitError_None;
        }

        void Cleanup() override {
            shim::uninstall();
            VR_CLEANUP_SERVER_DRIVER_CONTEXT();
        }

        const char* const* GetInterfaceVersions() override {
            return vr::k_InterfaceVersions;
        }

        void RunFrame() override {
            if (!m_attached.load()) {
                tryDirectAttach();
                return;
            }
            updateGaze();
            updateSupportProperty();
        }

        bool ShouldBlockStandbyMode() override {
            return false;
        }
        void EnterStandby() override {
        }
        void LeaveStandby() override {
        }

      private:
        void tryDirectAttach() {
            if (m_directTried || m_attached.load())
                return;
            vr::ETrackedPropertyError error = vr::TrackedProp_Success;
            const vr::PropertyContainerHandle_t container =
                vr::VRProperties()->TrackedDeviceToPropertyContainer(vr::k_unTrackedDeviceIndex_Hmd);
            const int32_t deviceClass =
                vr::VRProperties()->GetInt32Property(container, vr::Prop_DeviceClass_Int32, &error);
            if (error != vr::TrackedProp_Success || deviceClass != vr::TrackedDeviceClass_HMD)
                return; // no HMD yet
            m_directTried = true;
            attach(vr::k_unTrackedDeviceIndex_Hmd, "direct");
        }

        void attach(uint32_t deviceIndex, const char* route) {
            std::lock_guard lock(m_mutex);
            if (m_attached.load())
                return;
            m_container = vr::VRProperties()->TrackedDeviceToPropertyContainer(deviceIndex);
            vr::VRInputComponentHandle_t handle = vr::k_ulInvalidInputComponentHandle;
            const vr::EVRInputError error =
                vr::VRDriverInput()->CreateEyeTrackingComponent(m_container, kEyeTrackingPath, &handle);
            Log("Attach via %s to device %u: CreateEyeTrackingComponent -> %s (%d)",
                route,
                deviceIndex,
                inputErrorName(error),
                int(error));
            if (error != vr::VRInputError_None || handle == vr::k_ulInvalidInputComponentHandle)
                return;
            m_component = handle;
            m_supportAdvertised = -1;
            m_nextPropertyCheckNs = 0;
            m_attached = true;
        }

        void detach() {
            std::lock_guard lock(m_mutex);
            m_attached = false;
            m_component = vr::k_ulInvalidInputComponentHandle;
            m_directTried = false;
        }

        void updateGaze() {
            etvr_gaze gaze;
            const bool valid = m_gaze.read(gaze);
            if (valid && gaze.sample_count == m_lastSample)
                return; // nothing new since the last frame
            if (!valid && !m_lastValid)
                return; // still no gaze; already reported

            vr::VREyeTrackingData_t data{};
            data.bActive = m_gaze.published();
            data.bValid = valid;
            data.bTracked = valid;
            double timeOffset = 0.0;
            if (valid) {
                const etvr_gaze_eye& eye = gaze.eyes[ETVR_GAZE_EYE_COMBINED];
                // Both are in HMD space with OpenXR axes, which OpenVR shares (+X right, +Y up, -Z forward).
                data.vGazeOrigin = {{0.f, 0.f, 0.f}};
                data.vGazeTarget = {{eye.direction[0] * kTargetDistanceM,
                                     eye.direction[1] * kTargetDistanceM,
                                     eye.direction[2] * kTargetDistanceM}};
                // Negative: the sample is from the camera frame's capture time, in the past.
                timeOffset = -double(m_gaze.nowNs() - gaze.sample_time_ns) / 1e9;
                if (!(timeOffset <= 0.0) || timeOffset < -0.25)
                    timeOffset = 0.0;
                m_lastSample = gaze.sample_count;
            }
            m_lastValid = valid;

            const vr::EVRInputError error = vr::VRDriverInput()->UpdateEyeTrackingComponent(m_component, &data, timeOffset);
            if (error != vr::VRInputError_None && error != m_lastUpdateError)
                Log("UpdateEyeTrackingComponent -> %s (%d)", inputErrorName(error), int(error));
            m_lastUpdateError = error;
        }

        // Advertise eye gaze support only while EyeTrackVR publishes gaze, so apps started without
        // it keep their usual (fixed foveation) path. Apps read this when they start.
        void updateSupportProperty() {
            const int64_t now = m_gaze.nowNs();
            if (now < m_nextPropertyCheckNs)
                return;
            m_nextPropertyCheckNs = now + kPropertyCheckIntervalNs;
            const int supported = m_gaze.published() ? 1 : 0;
            if (supported == m_supportAdvertised)
                return;
            const vr::ETrackedPropertyError error =
                vr::VRProperties()->SetBoolProperty(m_container, vr::Prop_SupportsXrEyeGazeInteraction_Bool, supported != 0);
            Log("Prop_SupportsXrEyeGazeInteraction_Bool = %d -> %d", supported, int(error));
            m_supportAdvertised = supported;
        }

        std::mutex m_mutex;
        std::atomic<bool> m_attached{false};
        bool m_directTried{false};
        vr::PropertyContainerHandle_t m_container{vr::k_ulInvalidPropertyContainer};
        vr::VRInputComponentHandle_t m_component{vr::k_ulInvalidInputComponentHandle};
        GazeSource m_gaze;
        uint32_t m_lastSample{0};
        bool m_lastValid{false};
        vr::EVRInputError m_lastUpdateError{vr::VRInputError_None};
        int m_supportAdvertised{-1};
        int64_t m_nextPropertyCheckNs{0};
    };

} // namespace etvr

static etvr::EyeTrackVRProvider g_provider;

ETVR_EXPORT void* HmdDriverFactory(const char* pInterfaceName, int* pReturnCode) {
    if (std::strcmp(vr::IServerTrackedDeviceProvider_Version, pInterfaceName) == 0)
        return &g_provider;
    if (pReturnCode)
        *pReturnCode = vr::VRInitError_Init_InterfaceNotFound;
    return nullptr;
}
