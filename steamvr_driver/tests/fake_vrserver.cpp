// A minimal stand-in for vrserver: loads the real driver binary, registers a fake HMD the way
// a headset driver does, runs frames, and prints what reaches the eye tracking component.
//
//   fake_vrserver <driver .dll/.so> <shim|direct> [frames] [deny]
//     shim    HMD is added after the driver loads (goes through the patched TrackedDeviceAdded)
//     direct  HMD is added before the driver loads (driver must find it on its own)
//     deny    HMD container refuses other drivers' writes, like a strict vrserver might
//
// Output is one key=value line per event, for tests to parse.

#include <chrono>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>
#include <thread>

#include <openvr_driver.h>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <dlfcn.h>
#endif

using namespace vr;

namespace {

    constexpr PropertyContainerHandle_t kContainerBase = 1000;
    constexpr VRInputComponentHandle_t kEyeComponent = 42;
    bool g_deny = false;

    struct FakeLog : IVRDriverLog {
        void Log(const char* msg) override {
            std::printf("log=%s\n", msg);
        }
    } g_log;

    struct FakeProperties : IVRProperties {
        std::map<PropertyContainerHandle_t, std::map<int, int32_t>> ints;
        std::map<PropertyContainerHandle_t, std::map<int, bool>> bools;

        ETrackedPropertyError ReadPropertyBatch(PropertyContainerHandle_t c, PropertyRead_t* batch, uint32_t n) override {
            for (uint32_t i = 0; i < n; i++) {
                PropertyRead_t& r = batch[i];
                auto device = ints.find(c);
                if (device == ints.end() || !device->second.count(r.prop)) {
                    r.eError = TrackedProp_UnknownProperty;
                    continue;
                }
                r.unTag = k_unInt32PropertyTag;
                r.unRequiredBufferSize = sizeof(int32_t);
                if (r.unBufferSize < sizeof(int32_t)) {
                    r.eError = TrackedProp_BufferTooSmall;
                    continue;
                }
                *static_cast<int32_t*>(r.pvBuffer) = device->second[r.prop];
                r.eError = TrackedProp_Success;
            }
            return TrackedProp_Success;
        }
        ETrackedPropertyError WritePropertyBatch(PropertyContainerHandle_t c, PropertyWrite_t* batch, uint32_t n) override {
            for (uint32_t i = 0; i < n; i++) {
                PropertyWrite_t& w = batch[i];
                if (g_deny && c == kContainerBase) {
                    w.eError = w.eSetError = TrackedProp_PermissionDenied;
                    continue;
                }
                if (w.unTag == k_unBoolPropertyTag) {
                    bools[c][w.prop] = *static_cast<bool*>(w.pvBuffer);
                    std::printf("prop container=%llu prop=%d bool=%d\n", (unsigned long long)c, int(w.prop), int(bools[c][w.prop]));
                }
                w.eError = w.eSetError = TrackedProp_Success;
            }
            return g_deny && c == kContainerBase ? TrackedProp_PermissionDenied : TrackedProp_Success;
        }
        const char* GetPropErrorNameFromEnum(ETrackedPropertyError) override {
            return "";
        }
        PropertyContainerHandle_t TrackedDeviceToPropertyContainer(TrackedDeviceIndex_t index) override {
            return kContainerBase + index;
        }
    } g_properties;

    struct FakeInput : IVRDriverInput {
        int updates = 0;
        EVRInputError CreateBooleanComponent(PropertyContainerHandle_t, const char*, VRInputComponentHandle_t*) override { return VRInputError_None; }
        EVRInputError UpdateBooleanComponent(VRInputComponentHandle_t, bool, double) override { return VRInputError_None; }
        EVRInputError CreateScalarComponent(PropertyContainerHandle_t, const char*, VRInputComponentHandle_t*, EVRScalarType, EVRScalarUnits) override { return VRInputError_None; }
        EVRInputError UpdateScalarComponent(VRInputComponentHandle_t, float, double) override { return VRInputError_None; }
        EVRInputError CreateHapticComponent(PropertyContainerHandle_t, const char*, VRInputComponentHandle_t*) override { return VRInputError_None; }
        EVRInputError CreateSkeletonComponent(PropertyContainerHandle_t, const char*, const char*, const char*, EVRSkeletalTrackingLevel, const VRBoneTransform_t*, uint32_t, VRInputComponentHandle_t*) override { return VRInputError_None; }
        EVRInputError UpdateSkeletonComponent(VRInputComponentHandle_t, EVRSkeletalMotionRange, const VRBoneTransform_t*, uint32_t) override { return VRInputError_None; }
        EVRInputError CreatePoseComponent(PropertyContainerHandle_t, const char*, VRInputComponentHandle_t*) override { return VRInputError_None; }
        EVRInputError UpdatePoseComponent(VRInputComponentHandle_t, const HmdMatrix34_t*, double) override { return VRInputError_None; }
        EVRInputError CreateEyeTrackingComponent(PropertyContainerHandle_t c, const char* name, VRInputComponentHandle_t* handle) override {
            std::printf("create container=%llu name=%s\n", (unsigned long long)c, name);
            if (g_deny && c == kContainerBase)
                return VRInputError_PermissionDenied;
            *handle = kEyeComponent;
            return VRInputError_None;
        }
        EVRInputError UpdateEyeTrackingComponent(VRInputComponentHandle_t handle, const VREyeTrackingData_t* d, double offset) override {
            updates++;
            std::printf("update handle=%llu active=%d valid=%d tracked=%d origin=%.6f,%.6f,%.6f target=%.6f,%.6f,%.6f offset=%.6f\n",
                        (unsigned long long)handle, d->bActive, d->bValid, d->bTracked,
                        d->vGazeOrigin.v[0], d->vGazeOrigin.v[1], d->vGazeOrigin.v[2],
                        d->vGazeTarget.v[0], d->vGazeTarget.v[1], d->vGazeTarget.v[2], offset);
            std::fflush(stdout);
            return VRInputError_None;
        }
    } g_input;

    struct FakeHost : IVRServerDriverHost {
        ITrackedDeviceServerDriver* hmd = nullptr;
        bool TrackedDeviceAdded(const char* serial, ETrackedDeviceClass cls, ITrackedDeviceServerDriver* driver) override {
            std::printf("added serial=%s class=%d wrapped=%d\n", serial, int(cls), int(driver != pendingReal));
            if (cls == TrackedDeviceClass_HMD) {
                hmd = driver;
                g_properties.ints[kContainerBase][Prop_DeviceClass_Int32] = TrackedDeviceClass_HMD;
            }
            return true;
        }
        void TrackedDevicePoseUpdated(uint32_t, const DriverPose_t&, uint32_t) override {}
        void VsyncEvent(double) override {}
        void VendorSpecificEvent(uint32_t, EVREventType, const VREvent_Data_t&, double) override {}
        bool IsExiting() override { return false; }
        bool PollNextEvent(VREvent_t*, uint32_t) override { return false; }
        void GetRawTrackedDevicePoses(float, TrackedDevicePose_t*, uint32_t) override {}
        void RequestRestart(const char*, const char*, const char*, const char*) override {}
        uint32_t GetFrameTimings(Compositor_FrameTiming*, uint32_t) override { return 0; }
        void SetDisplayEyeToHead(uint32_t, const HmdMatrix34_t&, const HmdMatrix34_t&) override {}
        void SetDisplayProjectionRaw(uint32_t, const HmdRect2_t&, const HmdRect2_t&) override {}
        void SetRecommendedRenderTargetSize(uint32_t, uint32_t, uint32_t) override {}
        ITrackedDeviceServerDriver* pendingReal = nullptr;
    } g_host, g_otherDriverHost; // separate objects of one class, like vrserver's per-driver hosts

    struct FakeHmd : ITrackedDeviceServerDriver {
        int activations = 0;
        EVRInitError Activate(uint32_t id) override {
            activations++;
            std::printf("hmd_activate id=%u\n", id);
            return VRInitError_None;
        }
        void Deactivate() override { std::printf("hmd_deactivate\n"); }
        void EnterStandby() override {}
        void* GetComponent(const char* name) override { return std::strcmp(name, "probe") == 0 ? this : nullptr; }
        void DebugRequest(const char*, char* buf, uint32_t n) override { if (n) buf[0] = 0; }
        DriverPose_t GetPose() override { return {}; }
    } g_hmd;

    char g_dummy[64]; // settings / driver manager / resources: required non-null, never called here

    struct FakeContext : IVRDriverContext {
        void* GetGenericInterface(const char* version, EVRInitError* error) override {
            if (error)
                *error = VRInitError_None;
            if (!std::strcmp(version, IVRServerDriverHost_Version)) return static_cast<IVRServerDriverHost*>(&g_host);
            if (!std::strcmp(version, IVRProperties_Version)) return static_cast<IVRProperties*>(&g_properties);
            if (!std::strcmp(version, IVRDriverLog_Version)) return static_cast<IVRDriverLog*>(&g_log);
            if (!std::strcmp(version, IVRDriverInput_Version)) return static_cast<IVRDriverInput*>(&g_input);
            if (!std::strcmp(version, IVRSettings_Version) || !std::strcmp(version, IVRDriverManager_Version) ||
                !std::strcmp(version, IVRResources_Version))
                return g_dummy;
            if (error)
                *error = VRInitError_Init_InterfaceNotFound;
            return nullptr;
        }
        DriverHandle_t GetDriverHandle() override { return 1; }
    } g_context;

    // The headset's own driver registering its HMD through its own host object.
    void addHmd() {
        g_otherDriverHost.pendingReal = &g_hmd;
        // A real headset driver only has the interface pointer SteamVR gave it. volatile keeps the
        // compiler from seeing the concrete type and devirtualizing the call past the vtable.
        IVRServerDriverHost* volatile host = &g_otherDriverHost;
        host->TrackedDeviceAdded("FAKE-HMD-1", TrackedDeviceClass_HMD, &g_hmd);
        ITrackedDeviceServerDriver* registered = g_otherDriverHost.hmd ? g_otherDriverHost.hmd : &g_hmd;
        g_properties.ints[kContainerBase][Prop_DeviceClass_Int32] = TrackedDeviceClass_HMD;
        registered->Activate(0);
        std::printf("forwarded_component=%d\n", registered->GetComponent("probe") == &g_hmd);
    }

} // namespace

int main(int argc, char** argv) {
    if (argc < 3) {
        std::fprintf(stderr, "usage: fake_vrserver <driver> <shim|direct> [frames] [deny]\n");
        return 2;
    }
    const std::string mode = argv[2];
    const int frames = argc > 3 ? std::atoi(argv[3]) : 20;
    g_deny = argc > 4 && !std::strcmp(argv[4], "deny");

#ifdef _WIN32
    HMODULE lib = LoadLibraryA(argv[1]);
    auto factory = lib ? reinterpret_cast<void* (*)(const char*, int*)>(GetProcAddress(lib, "HmdDriverFactory")) : nullptr;
#else
    void* lib = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    auto factory = lib ? reinterpret_cast<void* (*)(const char*, int*)>(dlsym(lib, "HmdDriverFactory")) : nullptr;
#endif
    if (!factory) {
        std::printf("error=cannot load driver\n");
        return 1;
    }
    int code = 0;
    auto* provider = static_cast<IServerTrackedDeviceProvider*>(factory(IServerTrackedDeviceProvider_Version, &code));
    if (!provider) {
        std::printf("error=no provider (%d)\n", code);
        return 1;
    }

    if (mode == "direct")
        addHmd();
    const EVRInitError init = provider->Init(&g_context);
    std::printf("init=%d\n", int(init));
    if (mode == "shim")
        addHmd();

    for (int i = 0; i < frames; i++) {
        provider->RunFrame();
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    std::printf("hmd_activations=%d updates=%d\n", g_hmd.activations, g_input.updates);
    provider->Cleanup();
    std::printf("done\n");
    return 0;
}
