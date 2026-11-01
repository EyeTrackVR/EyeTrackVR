// Headless OpenXR app that uses XR_EXT_eye_gaze_interaction the way a game does, to test the
// layer against any runtime with XR_MND_headless (Monado, the fake test runtime).
//
//   gaze_probe [iterations]                          through the system OpenXR loader
//   gaze_probe [iterations] --direct <layer> <runtime>
//       no loader: load the layer and runtime libraries and chain them the way the loader does
//       (negotiate, XrApiLayerCreateInfo, the layer's xrGetInstanceProcAddr)
// Prints key=value lines. With EyeTrackVR (or a test writer) publishing gaze it should show
// supports=1, active=1 and a gaze forward vector matching the published direction.

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>
#include <chrono>
#include <vector>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <unknwn.h>
#define XR_USE_PLATFORM_WIN32
#else
#include <dlfcn.h>
#include <time.h>
#define XR_USE_TIMESPEC
#endif

// ETVR_PROBE_VULKAN=1 at run time (when built with Vulkan): a Vulkan session instead of a headless
// one, for runtimes that only focus real graphics sessions (Monado before late 2023).
#ifdef ETVR_PROBE_VULKAN
#include <vulkan/vulkan.h>
#define XR_USE_GRAPHICS_API_VULKAN
#endif

// Every OpenXR call goes through the function pointers below, named like the API.
#ifndef XR_NO_PROTOTYPES
#define XR_NO_PROTOTYPES
#endif
#include <openxr/openxr.h>
#include <openxr/openxr_loader_negotiation.h>
#include <openxr/openxr_platform.h>

#define CHECK(call)                                                                                                \
    do {                                                                                                           \
        XrResult r_ = (call);                                                                                      \
        if (XR_FAILED(r_)) {                                                                                       \
            std::printf("error=%s result=%d\n", #call, int(r_));                                                   \
            return 1;                                                                                              \
        }                                                                                                          \
    } while (0)

#define XR_FUNCTIONS(X)                                                                                            \
    X(xrDestroyInstance) X(xrGetInstanceProperties) X(xrGetSystem) X(xrGetSystemProperties) X(xrCreateSession)     \
    X(xrDestroySession) X(xrBeginSession) X(xrEndSession) X(xrPollEvent) X(xrStringToPath) X(xrCreateActionSet)    \
    X(xrWaitFrame) X(xrBeginFrame) X(xrEndFrame) X(xrRequestExitSession)                                           \
    X(xrCreateAction) X(xrSuggestInteractionProfileBindings) X(xrAttachSessionActionSets) X(xrCreateActionSpace)   \
    X(xrCreateReferenceSpace) X(xrDestroySpace) X(xrLocateSpace) X(xrSyncActions) X(xrGetActionStatePose)          \
    X(xrGetCurrentInteractionProfile) X(xrEnumerateBoundSourcesForAction) X(xrGetInputSourceLocalizedName)

PFN_xrGetInstanceProcAddr xrGetInstanceProcAddr;
PFN_xrEnumerateInstanceExtensionProperties xrEnumerateInstanceExtensionProperties;
PFN_xrCreateInstance xrCreateInstance;
#define DECLARE(f) PFN_##f f;
XR_FUNCTIONS(DECLARE)

namespace {
    void* openLibrary(const char* path) {
#ifdef _WIN32
        return LoadLibraryA(path);
#else
        return dlopen(path, RTLD_NOW | RTLD_LOCAL);
#endif
    }
    void* symbol(void* lib, const char* name) {
#ifdef _WIN32
        return reinterpret_cast<void*>(GetProcAddress(static_cast<HMODULE>(lib), name));
#else
        return dlsym(lib, name);
#endif
    }

    // --direct: what the loader would do for one layer on top of one runtime.
    PFN_xrGetInstanceProcAddr g_runtimeGipa;
    PFN_xrCreateApiLayerInstance g_layerCreate;
    PFN_xrEnumerateInstanceExtensionProperties g_runtimeEnumerate;

    XrResult XRAPI_CALL terminatorCreate(const XrInstanceCreateInfo* info, const XrApiLayerCreateInfo*, XrInstance* instance) {
        PFN_xrCreateInstance create = nullptr;
        g_runtimeGipa(XR_NULL_HANDLE, "xrCreateInstance", reinterpret_cast<PFN_xrVoidFunction*>(&create));
        return create(info, instance);
    }
    XrResult XRAPI_CALL directCreate(const XrInstanceCreateInfo* info, XrInstance* instance) {
        XrApiLayerNextInfo next{XR_LOADER_INTERFACE_STRUCT_API_LAYER_NEXT_INFO, XR_API_LAYER_NEXT_INFO_STRUCT_VERSION,
                                sizeof(XrApiLayerNextInfo)};
        std::strcpy(next.layerName, "XR_APILAYER_EYETRACKVR_eye_gaze");
        next.nextGetInstanceProcAddr = g_runtimeGipa;
        next.nextCreateApiLayerInstance = terminatorCreate;
        XrApiLayerCreateInfo create{XR_LOADER_INTERFACE_STRUCT_API_LAYER_CREATE_INFO,
                                    XR_API_LAYER_CREATE_INFO_STRUCT_VERSION, sizeof(XrApiLayerCreateInfo)};
        create.nextInfo = &next;
        return g_layerCreate(info, &create, instance);
    }
    // The loader adds the extensions a layer's manifest declares.
    XrResult XRAPI_CALL directEnumerate(const char* layer, uint32_t cap, uint32_t* count, XrExtensionProperties* props) {
        uint32_t n = 0;
        XrResult r = g_runtimeEnumerate(layer, 0, &n, nullptr);
        if (XR_FAILED(r))
            return r;
        *count = n + 1;
        if (!cap)
            return XR_SUCCESS;
        if (cap < *count)
            return XR_ERROR_SIZE_INSUFFICIENT;
        r = g_runtimeEnumerate(layer, n, &n, props);
        std::strcpy(props[n].extensionName, XR_EXT_EYE_GAZE_INTERACTION_EXTENSION_NAME);
        props[n].extensionVersion = 1;
        return r;
    }

    bool setUp(int argc, char** argv) {
        if (argc >= 5 && !std::strcmp(argv[2], "--direct")) {
            void* layer = openLibrary(argv[3]);
            void* runtime = openLibrary(argv[4]);
            auto negotiateLayer = layer ? reinterpret_cast<PFN_xrNegotiateLoaderApiLayerInterface>(
                                              symbol(layer, "xrNegotiateLoaderApiLayerInterface")) : nullptr;
            auto negotiateRuntime = runtime ? reinterpret_cast<PFN_xrNegotiateLoaderRuntimeInterface>(
                                                  symbol(runtime, "xrNegotiateLoaderRuntimeInterface")) : nullptr;
            if (!negotiateLayer || !negotiateRuntime) {
                std::printf("error=cannot load layer or runtime\n");
                return false;
            }
            XrNegotiateLoaderInfo info{XR_LOADER_INTERFACE_STRUCT_LOADER_INFO, XR_LOADER_INFO_STRUCT_VERSION,
                                       sizeof(XrNegotiateLoaderInfo), 1, 1, XR_MAKE_VERSION(1, 0, 0),
                                       XR_MAKE_VERSION(1, 1, 0)};
            XrNegotiateRuntimeRequest rt{XR_LOADER_INTERFACE_STRUCT_RUNTIME_REQUEST, XR_RUNTIME_INFO_STRUCT_VERSION,
                                         sizeof(XrNegotiateRuntimeRequest)};
            XrNegotiateApiLayerRequest ly{XR_LOADER_INTERFACE_STRUCT_API_LAYER_REQUEST, XR_API_LAYER_INFO_STRUCT_VERSION,
                                          sizeof(XrNegotiateApiLayerRequest)};
            if (XR_FAILED(negotiateRuntime(&info, &rt)) ||
                XR_FAILED(negotiateLayer(&info, "XR_APILAYER_EYETRACKVR_eye_gaze", &ly))) {
                std::printf("error=negotiation failed\n");
                return false;
            }
            g_runtimeGipa = rt.getInstanceProcAddr;
            g_layerCreate = ly.createApiLayerInstance;
            g_runtimeGipa(XR_NULL_HANDLE, "xrEnumerateInstanceExtensionProperties",
                          reinterpret_cast<PFN_xrVoidFunction*>(&g_runtimeEnumerate));
            xrGetInstanceProcAddr = ly.getInstanceProcAddr;
            xrEnumerateInstanceExtensionProperties = directEnumerate;
            xrCreateInstance = directCreate;
            std::printf("mode=direct\n");
            return true;
        }
#ifdef _WIN32
        void* loader = openLibrary("openxr_loader.dll");
#else
        void* loader = openLibrary("libopenxr_loader.so.1");
#endif
        xrGetInstanceProcAddr = loader ? reinterpret_cast<PFN_xrGetInstanceProcAddr>(symbol(loader, "xrGetInstanceProcAddr")) : nullptr;
        if (!xrGetInstanceProcAddr) {
            std::printf("error=no OpenXR loader\n");
            return false;
        }
        xrGetInstanceProcAddr(XR_NULL_HANDLE, "xrEnumerateInstanceExtensionProperties",
                              reinterpret_cast<PFN_xrVoidFunction*>(&xrEnumerateInstanceExtensionProperties));
        xrGetInstanceProcAddr(XR_NULL_HANDLE, "xrCreateInstance", reinterpret_cast<PFN_xrVoidFunction*>(&xrCreateInstance));
        std::printf("mode=loader\n");
        return xrEnumerateInstanceExtensionProperties && xrCreateInstance;
    }

    bool loadFunctions(XrInstance instance) {
        bool ok = true;
#define LOAD(f) ok &= XR_SUCCEEDED(xrGetInstanceProcAddr(instance, #f, reinterpret_cast<PFN_xrVoidFunction*>(&f)));
        XR_FUNCTIONS(LOAD)
        return ok;
    }

    XrVector3f forward(const XrQuaternionf& q) { // -Z rotated by q
        return {-(2.f * (q.x * q.z + q.w * q.y)), -(2.f * (q.y * q.z - q.w * q.x)), -(1.f - 2.f * (q.x * q.x + q.y * q.y))};
    }
    XrVector3f rotate(const XrQuaternionf& q, const XrVector3f& v) {
        const XrVector3f u{q.x, q.y, q.z};
        const float s = q.w;
        const float dot_uv = u.x * v.x + u.y * v.y + u.z * v.z, dot_uu = u.x * u.x + u.y * u.y + u.z * u.z;
        const XrVector3f cross{u.y * v.z - u.z * v.y, u.z * v.x - u.x * v.z, u.x * v.y - u.y * v.x};
        return {2.f * dot_uv * u.x + (s * s - dot_uu) * v.x + 2.f * s * cross.x,
                2.f * dot_uv * u.y + (s * s - dot_uu) * v.y + 2.f * s * cross.y,
                2.f * dot_uv * u.z + (s * s - dot_uu) * v.z + 2.f * s * cross.z};
    }
} // namespace

int main(int argc, char** argv) {
    const int iterations = argc > 1 ? std::atoi(argv[1]) : 10;
    if (!setUp(argc, argv))
        return 1;
#ifdef _WIN32
    const char* timeExt = XR_KHR_WIN32_CONVERT_PERFORMANCE_COUNTER_TIME_EXTENSION_NAME;
#else
    const char* timeExt = XR_KHR_CONVERT_TIMESPEC_TIME_EXTENSION_NAME;
#endif

    uint32_t count = 0;
    CHECK(xrEnumerateInstanceExtensionProperties(nullptr, 0, &count, nullptr));
    std::vector<XrExtensionProperties> exts(count, {XR_TYPE_EXTENSION_PROPERTIES});
    CHECK(xrEnumerateInstanceExtensionProperties(nullptr, count, &count, exts.data()));
#ifdef ETVR_PROBE_VULKAN
    const bool vulkan = std::getenv("ETVR_PROBE_VULKAN") != nullptr;
    const char* sessionExt = vulkan ? XR_KHR_VULKAN_ENABLE2_EXTENSION_NAME : XR_MND_HEADLESS_EXTENSION_NAME;
#else
    const char* sessionExt = XR_MND_HEADLESS_EXTENSION_NAME;
#endif
    bool hasGaze = false, hasSession = false, hasTime = false;
    for (const auto& e : exts) {
        hasGaze |= !std::strcmp(e.extensionName, XR_EXT_EYE_GAZE_INTERACTION_EXTENSION_NAME);
        hasSession |= !std::strcmp(e.extensionName, sessionExt);
        hasTime |= !std::strcmp(e.extensionName, timeExt);
    }
    std::printf("ext_eye_gaze=%d session_ext=%s:%d ext_time=%d\n", hasGaze, sessionExt, hasSession, hasTime);
    if (!hasGaze || !hasSession || !hasTime)
        return 1;

    const char* enabled[] = {XR_EXT_EYE_GAZE_INTERACTION_EXTENSION_NAME, sessionExt, timeExt};
    XrInstanceCreateInfo ici{XR_TYPE_INSTANCE_CREATE_INFO};
    std::snprintf(ici.applicationInfo.applicationName, XR_MAX_APPLICATION_NAME_SIZE, "EyeTrackVR gaze probe");
    ici.applicationInfo.apiVersion = XR_MAKE_VERSION(1, 0, 0); // also builds against older loader headers
    ici.enabledExtensionCount = 3;
    ici.enabledExtensionNames = enabled;
    XrInstance instance;
    CHECK(xrCreateInstance(&ici, &instance));
    if (!loadFunctions(instance)) {
        std::printf("error=missing OpenXR functions\n");
        return 1;
    }
    XrInstanceProperties ip{XR_TYPE_INSTANCE_PROPERTIES};
    xrGetInstanceProperties(instance, &ip);
    std::printf("runtime=%s\n", ip.runtimeName);

    XrSystemGetInfo sgi{XR_TYPE_SYSTEM_GET_INFO};
    sgi.formFactor = XR_FORM_FACTOR_HEAD_MOUNTED_DISPLAY;
    XrSystemId system;
    CHECK(xrGetSystem(instance, &sgi, &system));
    XrSystemEyeGazeInteractionPropertiesEXT eye{XR_TYPE_SYSTEM_EYE_GAZE_INTERACTION_PROPERTIES_EXT};
    XrSystemProperties sp{XR_TYPE_SYSTEM_PROPERTIES, &eye};
    CHECK(xrGetSystemProperties(instance, system, &sp));
    std::printf("system=%s supports=%d\n", sp.systemName, int(eye.supportsEyeGazeInteraction));

#ifdef _WIN32
    PFN_xrConvertWin32PerformanceCounterToTimeKHR toXrTime;
    CHECK(xrGetInstanceProcAddr(instance, "xrConvertWin32PerformanceCounterToTimeKHR", (PFN_xrVoidFunction*)&toXrTime));
    auto now = [&]() { LARGE_INTEGER c; QueryPerformanceCounter(&c); XrTime t = 0; toXrTime(instance, &c, &t); return t; };
#else
    PFN_xrConvertTimespecTimeToTimeKHR toXrTime;
    CHECK(xrGetInstanceProcAddr(instance, "xrConvertTimespecTimeToTimeKHR", (PFN_xrVoidFunction*)&toXrTime));
    auto now = [&]() { timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts); XrTime t = 0; toXrTime(instance, &ts, &t); return t; };
#endif

    XrSessionCreateInfo sci{XR_TYPE_SESSION_CREATE_INFO};
    sci.systemId = system;
#ifdef ETVR_PROBE_VULKAN
    // The runtime creates the Vulkan instance and device itself (XR_KHR_vulkan_enable2).
    XrGraphicsBindingVulkan2KHR binding2{XR_TYPE_GRAPHICS_BINDING_VULKAN2_KHR};
    if (vulkan) {
        PFN_xrGetVulkanGraphicsRequirements2KHR getReqs;
        PFN_xrCreateVulkanInstanceKHR createInstance;
        PFN_xrGetVulkanGraphicsDevice2KHR getDevice;
        PFN_xrCreateVulkanDeviceKHR createDevice;
        CHECK(xrGetInstanceProcAddr(instance, "xrGetVulkanGraphicsRequirements2KHR", (PFN_xrVoidFunction*)&getReqs));
        CHECK(xrGetInstanceProcAddr(instance, "xrCreateVulkanInstanceKHR", (PFN_xrVoidFunction*)&createInstance));
        CHECK(xrGetInstanceProcAddr(instance, "xrGetVulkanGraphicsDevice2KHR", (PFN_xrVoidFunction*)&getDevice));
        CHECK(xrGetInstanceProcAddr(instance, "xrCreateVulkanDeviceKHR", (PFN_xrVoidFunction*)&createDevice));
        XrGraphicsRequirementsVulkan2KHR reqs{XR_TYPE_GRAPHICS_REQUIREMENTS_VULKAN2_KHR};
        CHECK(getReqs(instance, system, &reqs));

        VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};
        app.pApplicationName = "EyeTrackVR gaze probe";
        app.apiVersion = VK_API_VERSION_1_1;
        VkInstanceCreateInfo vkInstanceInfo{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
        vkInstanceInfo.pApplicationInfo = &app;
        XrVulkanInstanceCreateInfoKHR xrInstanceInfo{XR_TYPE_VULKAN_INSTANCE_CREATE_INFO_KHR};
        xrInstanceInfo.systemId = system;
        xrInstanceInfo.pfnGetInstanceProcAddr = vkGetInstanceProcAddr;
        xrInstanceInfo.vulkanCreateInfo = &vkInstanceInfo;
        VkInstance vkInstance = VK_NULL_HANDLE;
        VkResult vkResult = VK_SUCCESS;
        CHECK(createInstance(instance, &xrInstanceInfo, &vkInstance, &vkResult));
        XrVulkanGraphicsDeviceGetInfoKHR deviceInfo{XR_TYPE_VULKAN_GRAPHICS_DEVICE_GET_INFO_KHR};
        deviceInfo.systemId = system;
        deviceInfo.vulkanInstance = vkInstance;
        VkPhysicalDevice physical = VK_NULL_HANDLE;
        CHECK(getDevice(instance, &deviceInfo, &physical));

        uint32_t families = 0;
        vkGetPhysicalDeviceQueueFamilyProperties(physical, &families, nullptr);
        std::vector<VkQueueFamilyProperties> props(families);
        vkGetPhysicalDeviceQueueFamilyProperties(physical, &families, props.data());
        uint32_t family = 0;
        while (family < families && !(props[family].queueFlags & VK_QUEUE_GRAPHICS_BIT))
            family++;
        const float priority = 1.f;
        VkDeviceQueueCreateInfo queueInfo{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
        queueInfo.queueFamilyIndex = family;
        queueInfo.queueCount = 1;
        queueInfo.pQueuePriorities = &priority;
        VkDeviceCreateInfo vkDeviceInfo{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
        vkDeviceInfo.queueCreateInfoCount = 1;
        vkDeviceInfo.pQueueCreateInfos = &queueInfo;
        XrVulkanDeviceCreateInfoKHR xrDeviceInfo{XR_TYPE_VULKAN_DEVICE_CREATE_INFO_KHR};
        xrDeviceInfo.systemId = system;
        xrDeviceInfo.pfnGetInstanceProcAddr = vkGetInstanceProcAddr;
        xrDeviceInfo.vulkanPhysicalDevice = physical;
        xrDeviceInfo.vulkanCreateInfo = &vkDeviceInfo;
        VkDevice device = VK_NULL_HANDLE;
        CHECK(createDevice(instance, &xrDeviceInfo, &device, &vkResult));

        binding2.instance = vkInstance;
        binding2.physicalDevice = physical;
        binding2.device = device;
        binding2.queueFamilyIndex = family;
        sci.next = &binding2;
        std::printf("graphics=vulkan\n");
    }
#endif
    XrSession session;
    CHECK(xrCreateSession(instance, &sci, &session));

    XrPath eyes, profile, gazePose;
    CHECK(xrStringToPath(instance, "/user/eyes_ext", &eyes));
    CHECK(xrStringToPath(instance, "/interaction_profiles/ext/eye_gaze_interaction", &profile));
    CHECK(xrStringToPath(instance, "/user/eyes_ext/input/gaze_ext/pose", &gazePose));

    XrActionSetCreateInfo asci{XR_TYPE_ACTION_SET_CREATE_INFO};
    std::strcpy(asci.actionSetName, "gaze");
    std::strcpy(asci.localizedActionSetName, "Gaze");
    XrActionSet set;
    CHECK(xrCreateActionSet(instance, &asci, &set));
    XrActionCreateInfo aci{XR_TYPE_ACTION_CREATE_INFO};
    aci.actionType = XR_ACTION_TYPE_POSE_INPUT;
    std::strcpy(aci.actionName, "gaze");
    std::strcpy(aci.localizedActionName, "Gaze");
    aci.countSubactionPaths = 1; // as the spec's sample does
    aci.subactionPaths = &eyes;
    XrAction gaze;
    CHECK(xrCreateAction(set, &aci, &gaze));
    XrActionSuggestedBinding binding{gaze, gazePose};
    XrInteractionProfileSuggestedBinding suggested{XR_TYPE_INTERACTION_PROFILE_SUGGESTED_BINDING};
    suggested.interactionProfile = profile;
    suggested.countSuggestedBindings = 1;
    suggested.suggestedBindings = &binding;
    CHECK(xrSuggestInteractionProfileBindings(instance, &suggested));
    XrSessionActionSetsAttachInfo attach{XR_TYPE_SESSION_ACTION_SETS_ATTACH_INFO};
    attach.countActionSets = 1;
    attach.actionSets = &set;
    CHECK(xrAttachSessionActionSets(session, &attach));

    XrActionSpaceCreateInfo aspci{XR_TYPE_ACTION_SPACE_CREATE_INFO};
    aspci.action = gaze;
    aspci.subactionPath = eyes;
    aspci.poseInActionSpace.orientation.w = 1.f;
    XrSpace gazeSpace, viewSpace, localSpace;
    CHECK(xrCreateActionSpace(session, &aspci, &gazeSpace));
    XrReferenceSpaceCreateInfo rsci{XR_TYPE_REFERENCE_SPACE_CREATE_INFO};
    rsci.poseInReferenceSpace.orientation.w = 1.f;
    rsci.referenceSpaceType = XR_REFERENCE_SPACE_TYPE_VIEW;
    CHECK(xrCreateReferenceSpace(session, &rsci, &viewSpace));
    rsci.referenceSpaceType = XR_REFERENCE_SPACE_TYPE_LOCAL;
    CHECK(xrCreateReferenceSpace(session, &rsci, &localSpace));

    // Session state machine and an empty frame loop, like a game. Runtimes such as Monado only
    // move a session past READY (and give it focus) once it submits frames, headless or not.
    XrSessionState state = XR_SESSION_STATE_UNKNOWN;
    bool running = false;
    auto pumpEvents = [&]() -> XrResult {
        XrEventDataBuffer ev{XR_TYPE_EVENT_DATA_BUFFER};
        while (xrPollEvent(instance, &ev) == XR_SUCCESS) {
            if (ev.type == XR_TYPE_EVENT_DATA_SESSION_STATE_CHANGED) {
                state = reinterpret_cast<XrEventDataSessionStateChanged*>(&ev)->state;
                std::printf("session_state=%d\n", int(state));
                if (state == XR_SESSION_STATE_READY && !running) {
                    XrSessionBeginInfo bi{XR_TYPE_SESSION_BEGIN_INFO};
                    bi.primaryViewConfigurationType = XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO;
                    const XrResult r = xrBeginSession(session, &bi);
                    if (XR_FAILED(r))
                        return r;
                    running = true;
                }
            }
            ev = {XR_TYPE_EVENT_DATA_BUFFER};
        }
        return XR_SUCCESS;
    };
    // One empty frame; returns the predicted display time (0 before the session runs).
    auto frame = [&]() -> XrTime {
        if (!running) {
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
            return 0;
        }
        XrFrameState fs{XR_TYPE_FRAME_STATE};
        if (XR_FAILED(xrWaitFrame(session, nullptr, &fs)) || XR_FAILED(xrBeginFrame(session, nullptr)))
            return 0;
        XrFrameEndInfo ei{XR_TYPE_FRAME_END_INFO};
        ei.displayTime = fs.predictedDisplayTime;
        ei.environmentBlendMode = XR_ENVIRONMENT_BLEND_MODE_OPAQUE;
        xrEndFrame(session, &ei);
        return fs.predictedDisplayTime;
    };
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
    while (state != XR_SESSION_STATE_FOCUSED && std::chrono::steady_clock::now() < deadline) {
        CHECK(pumpEvents());
        frame();
    }

    XrInteractionProfileState ips{XR_TYPE_INTERACTION_PROFILE_STATE};
    CHECK(xrGetCurrentInteractionProfile(session, eyes, &ips));
    std::printf("eyes_profile_is_eye_gaze=%d\n", int(ips.interactionProfile == profile));
    XrBoundSourcesForActionEnumerateInfo bse{XR_TYPE_BOUND_SOURCES_FOR_ACTION_ENUMERATE_INFO};
    bse.action = gaze;
    uint32_t sources = 0;
    CHECK(xrEnumerateBoundSourcesForAction(session, &bse, 0, &sources, nullptr));
    std::vector<XrPath> bound(sources);
    if (sources)
        CHECK(xrEnumerateBoundSourcesForAction(session, &bse, sources, &sources, bound.data()));
    char name[128] = "";
    if (sources) {
        XrInputSourceLocalizedNameGetInfo ln{XR_TYPE_INPUT_SOURCE_LOCALIZED_NAME_GET_INFO};
        ln.sourcePath = bound[0];
        ln.whichComponents = XR_INPUT_SOURCE_LOCALIZED_NAME_INTERACTION_PROFILE_BIT;
        uint32_t n = 0;
        xrGetInputSourceLocalizedName(session, &ln, sizeof(name), &n, name);
    }
    std::printf("bound_sources=%u first_is_gaze=%d name=%s\n", sources, int(sources && bound[0] == gazePose), name);

    for (int i = 0; i < iterations; i++) {
        XrActiveActionSet active{set, XR_NULL_PATH};
        XrActionsSyncInfo sync{XR_TYPE_ACTIONS_SYNC_INFO};
        sync.countActiveActionSets = 1;
        sync.activeActionSets = &active;
        const XrResult synced = xrSyncActions(session, &sync);
        XrActionStateGetInfo gi{XR_TYPE_ACTION_STATE_GET_INFO};
        gi.action = gaze;
        gi.subactionPath = eyes;
        XrActionStatePose ps{XR_TYPE_ACTION_STATE_POSE};
        CHECK(xrGetActionStatePose(session, &gi, &ps));

        CHECK(pumpEvents());
        XrTime t = frame();
        if (!t)
            t = now();
        XrEyeGazeSampleTimeEXT sample{XR_TYPE_EYE_GAZE_SAMPLE_TIME_EXT};
        XrSpaceLocation inView{XR_TYPE_SPACE_LOCATION, &sample};
        CHECK(xrLocateSpace(gazeSpace, viewSpace, t, &inView));
        XrSpaceLocation inLocal{XR_TYPE_SPACE_LOCATION};
        CHECK(xrLocateSpace(gazeSpace, localSpace, t, &inLocal));
        XrSpaceLocation head{XR_TYPE_SPACE_LOCATION};
        CHECK(xrLocateSpace(viewSpace, localSpace, t, &head));

        const XrVector3f fv = forward(inView.pose.orientation);
        const XrVector3f fl = forward(inLocal.pose.orientation);
        const XrVector3f expect = rotate(head.pose.orientation, fv); // view->local applied to gaze
        const float err = std::sqrt((fl.x - expect.x) * (fl.x - expect.x) + (fl.y - expect.y) * (fl.y - expect.y) +
                                    (fl.z - expect.z) * (fl.z - expect.z));
        const float posErr = std::sqrt(std::pow(inLocal.pose.position.x - head.pose.position.x, 2.f) +
                                       std::pow(inLocal.pose.position.y - head.pose.position.y, 2.f) +
                                       std::pow(inLocal.pose.position.z - head.pose.position.z, 2.f));
        std::printf("iter=%d sync=%d active=%d head_flags=%u view_flags=%u forward_view=%.6f,%.6f,%.6f local_flags=%u "
                    "forward_local=%.6f,%.6f,%.6f compose_err=%.6f pos_err=%.6f sample_age_ms=%.3f\n",
                    i, int(synced), int(ps.isActive), unsigned(head.locationFlags), unsigned(inView.locationFlags), fv.x, fv.y, fv.z,
                    unsigned(inLocal.locationFlags), fl.x, fl.y, fl.z, err, posErr,
                    sample.time ? double(t - sample.time) / 1e6 : -1.0);
        std::fflush(stdout);
    }

    xrDestroySpace(gazeSpace);
    xrDestroySpace(viewSpace);
    xrDestroySpace(localSpace);
    if (running) {
        xrRequestExitSession(session);
        const auto stopBy = std::chrono::steady_clock::now() + std::chrono::seconds(5);
        while (state != XR_SESSION_STATE_STOPPING && std::chrono::steady_clock::now() < stopBy) {
            pumpEvents();
            if (state != XR_SESSION_STATE_STOPPING)
                frame();
        }
        xrEndSession(session);
    }
    xrDestroySession(session);
    xrDestroyInstance(instance);
    std::printf("done\n");
    return 0;
}
