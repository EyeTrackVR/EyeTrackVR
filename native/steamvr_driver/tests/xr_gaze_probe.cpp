// OpenXR end-to-end check for the driver: does the active runtime (SteamVR) advertise
// XR_EXT_eye_gaze_interaction, and does /user/eyes_ext/input/gaze_ext/pose follow EyeTrackVR?
// Windows / D3D11 only; it submits empty frames, so nothing shows in the headset.
//
//   xr_gaze_probe [seconds]
// Prints key=value lines.

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <d3d11.h>

#define XR_USE_PLATFORM_WIN32
#define XR_USE_GRAPHICS_API_D3D11
#include <openxr/openxr.h>
#include <openxr/openxr_platform.h>

#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <vector>

#define CHECK(call)                                                                                                \
    do {                                                                                                           \
        XrResult r_ = (call);                                                                                      \
        if (XR_FAILED(r_)) {                                                                                       \
            std::printf("error=%s -> %d\n", #call, int(r_));                                                       \
            return 1;                                                                                              \
        }                                                                                                          \
    } while (0)

int main(int argc, char** argv) {
    const double seconds = argc > 1 ? std::atof(argv[1]) : 5.0;

    uint32_t count = 0;
    CHECK(xrEnumerateInstanceExtensionProperties(nullptr, 0, &count, nullptr));
    std::vector<XrExtensionProperties> extensions(count, {XR_TYPE_EXTENSION_PROPERTIES});
    CHECK(xrEnumerateInstanceExtensionProperties(nullptr, count, &count, extensions.data()));
    bool hasEyeGaze = false, hasD3D11 = false;
    for (const auto& e : extensions) {
        hasEyeGaze |= !std::strcmp(e.extensionName, XR_EXT_EYE_GAZE_INTERACTION_EXTENSION_NAME);
        hasD3D11 |= !std::strcmp(e.extensionName, XR_KHR_D3D11_ENABLE_EXTENSION_NAME);
    }
    std::printf("ext_eye_gaze_interaction=%d ext_d3d11=%d\n", hasEyeGaze, hasD3D11);
    if (!hasEyeGaze || !hasD3D11)
        return 1;

    const char* enabled[] = {XR_EXT_EYE_GAZE_INTERACTION_EXTENSION_NAME, XR_KHR_D3D11_ENABLE_EXTENSION_NAME};
    XrInstanceCreateInfo ici{XR_TYPE_INSTANCE_CREATE_INFO};
    std::strcpy(ici.applicationInfo.applicationName, "EyeTrackVR gaze probe");
    ici.applicationInfo.apiVersion = XR_MAKE_VERSION(1, 0, 0);
    ici.enabledExtensionCount = 2;
    ici.enabledExtensionNames = enabled;
    XrInstance instance;
    CHECK(xrCreateInstance(&ici, &instance));

    XrInstanceProperties ip{XR_TYPE_INSTANCE_PROPERTIES};
    xrGetInstanceProperties(instance, &ip);
    std::printf("runtime=%s\n", ip.runtimeName);

    XrSystemGetInfo sgi{XR_TYPE_SYSTEM_GET_INFO};
    sgi.formFactor = XR_FORM_FACTOR_HEAD_MOUNTED_DISPLAY;
    XrSystemId system;
    CHECK(xrGetSystem(instance, &sgi, &system));
    XrSystemEyeGazeInteractionPropertiesEXT eyeProps{XR_TYPE_SYSTEM_EYE_GAZE_INTERACTION_PROPERTIES_EXT};
    XrSystemProperties sp{XR_TYPE_SYSTEM_PROPERTIES, &eyeProps};
    CHECK(xrGetSystemProperties(instance, system, &sp));
    std::printf("system=%s supportsEyeGazeInteraction=%d\n", sp.systemName, int(eyeProps.supportsEyeGazeInteraction));

    // D3D11 device on the runtime's adapter.
    PFN_xrGetD3D11GraphicsRequirementsKHR getReqs;
    CHECK(xrGetInstanceProcAddr(instance, "xrGetD3D11GraphicsRequirementsKHR", (PFN_xrVoidFunction*)&getReqs));
    XrGraphicsRequirementsD3D11KHR reqs{XR_TYPE_GRAPHICS_REQUIREMENTS_D3D11_KHR};
    CHECK(getReqs(instance, system, &reqs));
    ID3D11Device* device = nullptr;
    D3D_FEATURE_LEVEL level = reqs.minFeatureLevel;
    if (FAILED(D3D11CreateDevice(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr, 0, &level, 1, D3D11_SDK_VERSION, &device, nullptr, nullptr))) {
        std::printf("error=D3D11CreateDevice\n");
        return 1;
    }
    XrGraphicsBindingD3D11KHR binding{XR_TYPE_GRAPHICS_BINDING_D3D11_KHR};
    binding.device = device;
    XrSessionCreateInfo sci{XR_TYPE_SESSION_CREATE_INFO, &binding};
    sci.systemId = system;
    XrSession session;
    CHECK(xrCreateSession(instance, &sci, &session));

    // Eye gaze pose action.
    XrActionSetCreateInfo asci{XR_TYPE_ACTION_SET_CREATE_INFO};
    std::strcpy(asci.actionSetName, "gaze");
    std::strcpy(asci.localizedActionSetName, "Gaze");
    XrActionSet actionSet;
    CHECK(xrCreateActionSet(instance, &asci, &actionSet));
    XrActionCreateInfo aci{XR_TYPE_ACTION_CREATE_INFO};
    aci.actionType = XR_ACTION_TYPE_POSE_INPUT;
    std::strcpy(aci.actionName, "gaze");
    std::strcpy(aci.localizedActionName, "Gaze");
    XrAction gazeAction;
    CHECK(xrCreateAction(actionSet, &aci, &gazeAction));
    XrPath profile, gazePath;
    CHECK(xrStringToPath(instance, "/interaction_profiles/ext/eye_gaze_interaction", &profile));
    CHECK(xrStringToPath(instance, "/user/eyes_ext/input/gaze_ext/pose", &gazePath));
    XrActionSuggestedBinding sb{gazeAction, gazePath};
    XrInteractionProfileSuggestedBinding ipsb{XR_TYPE_INTERACTION_PROFILE_SUGGESTED_BINDING};
    ipsb.interactionProfile = profile;
    ipsb.countSuggestedBindings = 1;
    ipsb.suggestedBindings = &sb;
    CHECK(xrSuggestInteractionProfileBindings(instance, &ipsb));
    XrSessionActionSetsAttachInfo attach{XR_TYPE_SESSION_ACTION_SETS_ATTACH_INFO};
    attach.countActionSets = 1;
    attach.actionSets = &actionSet;
    CHECK(xrAttachSessionActionSets(session, &attach));

    XrActionSpaceCreateInfo aspci{XR_TYPE_ACTION_SPACE_CREATE_INFO};
    aspci.action = gazeAction;
    aspci.poseInActionSpace.orientation.w = 1.f;
    XrSpace gazeSpace, viewSpace;
    CHECK(xrCreateActionSpace(session, &aspci, &gazeSpace));
    XrReferenceSpaceCreateInfo rsci{XR_TYPE_REFERENCE_SPACE_CREATE_INFO};
    rsci.referenceSpaceType = XR_REFERENCE_SPACE_TYPE_VIEW;
    rsci.poseInReferenceSpace.orientation.w = 1.f;
    CHECK(xrCreateReferenceSpace(session, &rsci, &viewSpace));

    bool running = false;
    int located = 0, frames = 0;
    const auto start = std::chrono::steady_clock::now();
    while (std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count() < seconds) {
        XrEventDataBuffer event{XR_TYPE_EVENT_DATA_BUFFER};
        while (xrPollEvent(instance, &event) == XR_SUCCESS) {
            if (event.type == XR_TYPE_EVENT_DATA_SESSION_STATE_CHANGED) {
                const auto* s = reinterpret_cast<XrEventDataSessionStateChanged*>(&event);
                std::printf("session_state=%d\n", int(s->state));
                if (s->state == XR_SESSION_STATE_READY) {
                    XrSessionBeginInfo bi{XR_TYPE_SESSION_BEGIN_INFO};
                    bi.primaryViewConfigurationType = XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO;
                    CHECK(xrBeginSession(session, &bi));
                    running = true;
                }
            }
            event = {XR_TYPE_EVENT_DATA_BUFFER};
        }
        if (!running) {
            Sleep(10);
            continue;
        }
        XrFrameState fs{XR_TYPE_FRAME_STATE};
        CHECK(xrWaitFrame(session, nullptr, &fs));
        CHECK(xrBeginFrame(session, nullptr));

        XrActiveActionSet active{actionSet, XR_NULL_PATH};
        XrActionsSyncInfo sync{XR_TYPE_ACTIONS_SYNC_INFO};
        sync.countActiveActionSets = 1;
        sync.activeActionSets = &active;
        xrSyncActions(session, &sync);
        XrActionStatePose state{XR_TYPE_ACTION_STATE_POSE};
        XrActionStateGetInfo gi{XR_TYPE_ACTION_STATE_GET_INFO};
        gi.action = gazeAction;
        xrGetActionStatePose(session, &gi, &state);

        XrSpaceLocation loc{XR_TYPE_SPACE_LOCATION};
        xrLocateSpace(gazeSpace, viewSpace, fs.predictedDisplayTime, &loc);
        const bool ok = (loc.locationFlags & XR_SPACE_LOCATION_ORIENTATION_VALID_BIT) != 0;
        if (frames % 30 == 0 || (ok && located == 0)) {
            // Forward (-Z) rotated by the gaze orientation.
            const XrQuaternionf q = loc.pose.orientation;
            const float x = -(2.f * (q.x * q.z + q.w * q.y));
            const float y = -(2.f * (q.y * q.z - q.w * q.x));
            const float z = -(1.f - 2.f * (q.x * q.x + q.y * q.y));
            std::printf("frame=%d active=%d orientation_valid=%d forward=%.6f,%.6f,%.6f\n",
                        frames, int(state.isActive), int(ok), x, y, z);
            std::fflush(stdout);
        }
        located += ok;
        frames++;

        XrFrameEndInfo ei{XR_TYPE_FRAME_END_INFO};
        ei.displayTime = fs.predictedDisplayTime;
        ei.environmentBlendMode = XR_ENVIRONMENT_BLEND_MODE_OPAQUE;
        CHECK(xrEndFrame(session, &ei));
    }
    std::printf("frames=%d located=%d\n", frames, located);
    if (running)
        xrEndSession(session);
    xrDestroySession(session);
    xrDestroyInstance(instance);
    device->Release();
    return 0;
}
