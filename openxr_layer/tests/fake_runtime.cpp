// A tiny, strict OpenXR runtime for testing the layer through the real loader. Headless only.
// It is strict where the layer must cover for real runtimes: no XR_EXT_eye_gaze_interaction,
// rejects /user/eyes_ext, the eye gaze profile, and unknown structs in xrGetSystemProperties.
// The head (VIEW in LOCAL) sits at (0, 1.6, 0) turned 30 degrees left.
//
// FAKE_RUNTIME_EYE_GAZE=1 makes it offer the extension itself (the layer must then stay out).

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <thread>
#include <vector>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <unknwn.h>
#define XR_USE_PLATFORM_WIN32
#define RT_EXPORT extern "C" __declspec(dllexport)
#else
#include <time.h>
#define XR_USE_TIMESPEC
#define RT_EXPORT extern "C" __attribute__((visibility("default")))
#endif

#include <openxr/openxr.h>
#include <openxr/openxr_loader_negotiation.h>
#include <openxr/openxr_platform.h>

namespace {

    const bool g_hasEyeGaze = std::getenv("FAKE_RUNTIME_EYE_GAZE") != nullptr;
#ifdef _WIN32
    const char* kTimeExt = XR_KHR_WIN32_CONVERT_PERFORMANCE_COUNTER_TIME_EXTENSION_NAME;
#else
    const char* kTimeExt = XR_KHR_CONVERT_TIMESPEC_TIME_EXTENSION_NAME;
#endif

    struct Space {
        XrReferenceSpaceType type;
        bool action;
        XrPosef pose;
    };
    struct Session {
        std::deque<XrSessionState> events;
    };

    std::mutex g_mutex;
    std::vector<std::string> g_paths{""};
    std::set<std::string> g_enabled;
    std::map<XrSpace, Space> g_spaces;
    std::map<XrSession, Session> g_sessions;
    std::atomic<uint64_t> g_next{1};

    template <typename H>
    H newHandle() {
        return reinterpret_cast<H>(uintptr_t(g_next++ * 16));
    }

    std::vector<const char*> extensions() {
        std::vector<const char*> e{XR_MND_HEADLESS_EXTENSION_NAME, kTimeExt};
        if (g_hasEyeGaze)
            e.push_back(XR_EXT_EYE_GAZE_INTERACTION_EXTENSION_NAME);
        return e;
    }

    std::string pathString(XrPath p) {
        std::lock_guard lock(g_mutex);
        return p < g_paths.size() ? g_paths[size_t(p)] : "";
    }

    XrQuaternionf yaw(float degrees) {
        const float h = degrees * 3.14159265f / 360.f;
        return {0.f, std::sin(h), 0.f, std::cos(h)};
    }
    XrQuaternionf mul(const XrQuaternionf& a, const XrQuaternionf& b) {
        return {a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y, a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
                a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w, a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z};
    }
    XrVector3f rot(const XrQuaternionf& q, const XrVector3f& v) {
        const XrQuaternionf c{-q.x, -q.y, -q.z, q.w};
        const XrQuaternionf p = mul(mul(q, {v.x, v.y, v.z, 0.f}), c);
        return {p.x, p.y, p.z};
    }
    XrPosef compose(const XrPosef& a, const XrPosef& b) {
        const XrVector3f t = rot(a.orientation, b.position);
        return {mul(a.orientation, b.orientation), {a.position.x + t.x, a.position.y + t.y, a.position.z + t.z}};
    }
    XrPosef inv(const XrPosef& p) {
        const XrQuaternionf q{-p.orientation.x, -p.orientation.y, -p.orientation.z, p.orientation.w};
        const XrVector3f t = rot(q, p.position);
        return {q, {-t.x, -t.y, -t.z}};
    }
    // A reference space's pose in LOCAL.
    XrPosef inLocal(const Space& s) {
        const XrPosef head{yaw(30.f), {0.f, 1.6f, 0.f}};
        const XrPosef origin = s.type == XR_REFERENCE_SPACE_TYPE_VIEW ? head : XrPosef{{0, 0, 0, 1}, {0, 0, 0}};
        return compose(origin, s.pose);
    }

    int64_t nowNs() {
#ifdef _WIN32
        LARGE_INTEGER c, f;
        QueryPerformanceCounter(&c);
        QueryPerformanceFrequency(&f);
        return (c.QuadPart / f.QuadPart) * 1000000000LL + (c.QuadPart % f.QuadPart) * 1000000000LL / f.QuadPart;
#else
        timespec ts;
        clock_gettime(CLOCK_MONOTONIC, &ts);
        return int64_t(ts.tv_sec) * 1000000000LL + ts.tv_nsec;
#endif
    }

    // ---------------------------------------------------------------- API

    XrResult XRAPI_CALL rt_xrEnumerateInstanceExtensionProperties(const char* layer, uint32_t cap, uint32_t* count,
                                                                  XrExtensionProperties* props) {
        if (layer)
            return XR_ERROR_API_LAYER_NOT_PRESENT;
        const auto e = extensions();
        *count = uint32_t(e.size());
        if (!cap)
            return XR_SUCCESS;
        if (cap < e.size())
            return XR_ERROR_SIZE_INSUFFICIENT;
        for (size_t i = 0; i < e.size(); i++) {
            std::strncpy(props[i].extensionName, e[i], XR_MAX_EXTENSION_NAME_SIZE);
            props[i].extensionVersion = 1;
        }
        return XR_SUCCESS;
    }

    XrResult XRAPI_CALL rt_xrCreateInstance(const XrInstanceCreateInfo* info, XrInstance* instance) {
        const auto supported = extensions();
        std::lock_guard lock(g_mutex);
        g_enabled.clear();
        for (uint32_t i = 0; i < info->enabledExtensionCount; i++) {
            const char* e = info->enabledExtensionNames[i];
            bool ok = false;
            for (const char* s : supported)
                ok |= !std::strcmp(s, e);
            if (!ok)
                return XR_ERROR_EXTENSION_NOT_PRESENT;
            g_enabled.insert(e);
        }
        *instance = newHandle<XrInstance>();
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrDestroyInstance(XrInstance) {
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrGetInstanceProperties(XrInstance, XrInstanceProperties* p) {
        p->runtimeVersion = XR_MAKE_VERSION(0, 1, 0);
        std::strncpy(p->runtimeName, "EyeTrackVR fake runtime", XR_MAX_RUNTIME_NAME_SIZE);
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrGetSystem(XrInstance, const XrSystemGetInfo* info, XrSystemId* id) {
        if (info->formFactor != XR_FORM_FACTOR_HEAD_MOUNTED_DISPLAY)
            return XR_ERROR_FORM_FACTOR_UNSUPPORTED;
        *id = 1;
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrGetSystemProperties(XrInstance, XrSystemId, XrSystemProperties* p) {
        for (auto* s = static_cast<XrBaseOutStructure*>(p->next); s; s = s->next) {
            if (s->type == XR_TYPE_SYSTEM_EYE_GAZE_INTERACTION_PROPERTIES_EXT) {
                std::lock_guard lock(g_mutex);
                if (!g_enabled.count(XR_EXT_EYE_GAZE_INTERACTION_EXTENSION_NAME))
                    return XR_ERROR_VALIDATION_FAILURE; // strict: struct of an extension not enabled
                reinterpret_cast<XrSystemEyeGazeInteractionPropertiesEXT*>(s)->supportsEyeGazeInteraction = XR_TRUE;
            }
        }
        p->systemId = 1;
        std::strncpy(p->systemName, "Fake HMD", XR_MAX_SYSTEM_NAME_SIZE);
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrStringToPath(XrInstance, const char* s, XrPath* path) {
        if (!s || s[0] != '/')
            return XR_ERROR_PATH_FORMAT_INVALID;
        std::lock_guard lock(g_mutex);
        for (size_t i = 1; i < g_paths.size(); i++)
            if (g_paths[i] == s) {
                *path = XrPath(i);
                return XR_SUCCESS;
            }
        g_paths.push_back(s);
        *path = XrPath(g_paths.size() - 1);
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrPathToString(XrInstance, XrPath path, uint32_t cap, uint32_t* count, char* buf) {
        const std::string s = pathString(path);
        if (s.empty())
            return XR_ERROR_PATH_INVALID;
        *count = uint32_t(s.size() + 1);
        if (!cap)
            return XR_SUCCESS;
        if (cap < *count)
            return XR_ERROR_SIZE_INSUFFICIENT;
        std::memcpy(buf, s.c_str(), *count);
        return XR_SUCCESS;
    }
    bool knownTopLevel(XrPath p) {
        const std::string s = pathString(p);
        return s == "/user/hand/left" || s == "/user/hand/right" || s == "/user/head" ||
               (g_hasEyeGaze && s == "/user/eyes_ext");
    }
    XrResult XRAPI_CALL rt_xrCreateActionSet(XrInstance, const XrActionSetCreateInfo*, XrActionSet* set) {
        *set = newHandle<XrActionSet>();
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrDestroyActionSet(XrActionSet) {
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrCreateAction(XrActionSet, const XrActionCreateInfo* info, XrAction* action) {
        for (uint32_t i = 0; i < info->countSubactionPaths; i++)
            if (!knownTopLevel(info->subactionPaths[i]))
                return XR_ERROR_PATH_UNSUPPORTED;
        *action = newHandle<XrAction>();
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrDestroyAction(XrAction) {
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrSuggestInteractionProfileBindings(XrInstance, const XrInteractionProfileSuggestedBinding* b) {
        const std::string p = pathString(b->interactionProfile);
        if (p == "/interaction_profiles/khr/simple_controller" ||
            (g_hasEyeGaze && p == "/interaction_profiles/ext/eye_gaze_interaction"))
            return XR_SUCCESS;
        return XR_ERROR_PATH_UNSUPPORTED;
    }
    XrResult XRAPI_CALL rt_xrAttachSessionActionSets(XrSession, const XrSessionActionSetsAttachInfo*) {
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrCreateSession(XrInstance, const XrSessionCreateInfo* info, XrSession* session) {
        bool headless = false;
        {
            std::lock_guard lock(g_mutex);
            headless = g_enabled.count(XR_MND_HEADLESS_EXTENSION_NAME) != 0;
        }
        if (!headless || info->next)
            return XR_ERROR_GRAPHICS_DEVICE_INVALID;
        *session = newHandle<XrSession>();
        std::lock_guard lock(g_mutex);
        g_sessions[*session].events = {XR_SESSION_STATE_IDLE, XR_SESSION_STATE_READY};
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrDestroySession(XrSession s) {
        std::lock_guard lock(g_mutex);
        g_sessions.erase(s);
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrBeginSession(XrSession s, const XrSessionBeginInfo*) {
        std::lock_guard lock(g_mutex);
        for (auto st : {XR_SESSION_STATE_SYNCHRONIZED, XR_SESSION_STATE_VISIBLE, XR_SESSION_STATE_FOCUSED})
            g_sessions[s].events.push_back(st);
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrEndSession(XrSession) {
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrRequestExitSession(XrSession s) {
        std::lock_guard lock(g_mutex);
        for (auto st : {XR_SESSION_STATE_VISIBLE, XR_SESSION_STATE_SYNCHRONIZED, XR_SESSION_STATE_STOPPING})
            g_sessions[s].events.push_back(st);
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrWaitFrame(XrSession, const XrFrameWaitInfo*, XrFrameState* fs) {
        std::this_thread::sleep_for(std::chrono::milliseconds(11)); // ~90 Hz
        fs->predictedDisplayPeriod = 11'111'111;
        fs->predictedDisplayTime = nowNs() + fs->predictedDisplayPeriod;
        fs->shouldRender = XR_TRUE;
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrBeginFrame(XrSession, const XrFrameBeginInfo*) {
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrEndFrame(XrSession, const XrFrameEndInfo* info) {
        return info->layerCount == 0 ? XR_SUCCESS : XR_ERROR_LAYER_INVALID; // headless: nothing to show
    }
    XrResult XRAPI_CALL rt_xrPollEvent(XrInstance, XrEventDataBuffer* buf) {
        std::lock_guard lock(g_mutex);
        for (auto& [handle, s] : g_sessions) {
            if (s.events.empty())
                continue;
            auto* e = reinterpret_cast<XrEventDataSessionStateChanged*>(buf);
            *e = {XR_TYPE_EVENT_DATA_SESSION_STATE_CHANGED};
            e->session = handle;
            e->state = s.events.front();
            e->time = nowNs();
            s.events.pop_front();
            return XR_SUCCESS;
        }
        return XR_EVENT_UNAVAILABLE;
    }
    XrResult XRAPI_CALL rt_xrCreateReferenceSpace(XrSession, const XrReferenceSpaceCreateInfo* info, XrSpace* space) {
        *space = newHandle<XrSpace>();
        std::lock_guard lock(g_mutex);
        g_spaces[*space] = {info->referenceSpaceType, false, info->poseInReferenceSpace};
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrCreateActionSpace(XrSession, const XrActionSpaceCreateInfo* info, XrSpace* space) {
        if (info->subactionPath != XR_NULL_PATH && !knownTopLevel(info->subactionPath))
            return XR_ERROR_PATH_UNSUPPORTED;
        *space = newHandle<XrSpace>();
        std::lock_guard lock(g_mutex);
        g_spaces[*space] = {XR_REFERENCE_SPACE_TYPE_LOCAL, true, info->poseInActionSpace};
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrDestroySpace(XrSpace space) {
        std::lock_guard lock(g_mutex);
        return g_spaces.erase(space) ? XR_SUCCESS : XR_ERROR_HANDLE_INVALID;
    }
    XrResult XRAPI_CALL rt_xrLocateSpace(XrSpace space, XrSpace base, XrTime, XrSpaceLocation* loc) {
        std::lock_guard lock(g_mutex);
        auto a = g_spaces.find(space), b = g_spaces.find(base);
        if (a == g_spaces.end() || b == g_spaces.end())
            return XR_ERROR_HANDLE_INVALID;
        const bool gazeEnabled = g_enabled.count(XR_EXT_EYE_GAZE_INTERACTION_EXTENSION_NAME) != 0;
        for (auto* s = static_cast<XrBaseOutStructure*>(loc->next); s; s = s->next)
            if (s->type != XR_TYPE_SPACE_VELOCITY && !(gazeEnabled && s->type == XR_TYPE_EYE_GAZE_SAMPLE_TIME_EXT))
                return XR_ERROR_VALIDATION_FAILURE; // strict: XrEyeGazeSampleTimeEXT without the extension
        loc->locationFlags = 0;
        loc->pose = {{0, 0, 0, 1}, {0, 0, 0}};
        if (a->second.action || b->second.action)
            return XR_SUCCESS; // nothing bound in this runtime
        loc->pose = compose(inv(inLocal(b->second)), inLocal(a->second));
        loc->locationFlags = XR_SPACE_LOCATION_ORIENTATION_VALID_BIT | XR_SPACE_LOCATION_POSITION_VALID_BIT |
                             XR_SPACE_LOCATION_ORIENTATION_TRACKED_BIT | XR_SPACE_LOCATION_POSITION_TRACKED_BIT;
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrSyncActions(XrSession, const XrActionsSyncInfo*) {
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrGetActionStatePose(XrSession, const XrActionStateGetInfo* info, XrActionStatePose* st) {
        if (info->subactionPath != XR_NULL_PATH && !knownTopLevel(info->subactionPath))
            return XR_ERROR_PATH_UNSUPPORTED;
        st->isActive = XR_FALSE;
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrGetCurrentInteractionProfile(XrSession, XrPath top, XrInteractionProfileState* st) {
        if (!knownTopLevel(top))
            return XR_ERROR_PATH_UNSUPPORTED;
        st->interactionProfile = XR_NULL_PATH;
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrEnumerateBoundSourcesForAction(XrSession, const XrBoundSourcesForActionEnumerateInfo*,
                                                            uint32_t, uint32_t* count, XrPath*) {
        *count = 0;
        return XR_SUCCESS;
    }
    XrResult XRAPI_CALL rt_xrGetInputSourceLocalizedName(XrSession, const XrInputSourceLocalizedNameGetInfo*, uint32_t,
                                                         uint32_t*, char*) {
        return XR_ERROR_PATH_UNSUPPORTED;
    }
#ifdef _WIN32
    XrResult XRAPI_CALL rt_xrConvertWin32PerformanceCounterToTimeKHR(XrInstance, const LARGE_INTEGER* c, XrTime* t) {
        LARGE_INTEGER f;
        QueryPerformanceFrequency(&f);
        *t = (c->QuadPart / f.QuadPart) * 1000000000LL + (c->QuadPart % f.QuadPart) * 1000000000LL / f.QuadPart;
        return XR_SUCCESS;
    }
#else
    XrResult XRAPI_CALL rt_xrConvertTimespecTimeToTimeKHR(XrInstance, const timespec* ts, XrTime* t) {
        *t = int64_t(ts->tv_sec) * 1000000000LL + ts->tv_nsec;
        return XR_SUCCESS;
    }
#endif

#define FN(f) {#f, reinterpret_cast<PFN_xrVoidFunction>(rt_##f)}
    const std::map<std::string, PFN_xrVoidFunction> kFunctions = {
        FN(xrEnumerateInstanceExtensionProperties), FN(xrCreateInstance), FN(xrDestroyInstance),
        FN(xrGetInstanceProperties), FN(xrGetSystem), FN(xrGetSystemProperties), FN(xrStringToPath),
        FN(xrPathToString), FN(xrCreateActionSet), FN(xrDestroyActionSet), FN(xrCreateAction),
        FN(xrDestroyAction), FN(xrSuggestInteractionProfileBindings), FN(xrAttachSessionActionSets),
        FN(xrCreateSession), FN(xrDestroySession), FN(xrBeginSession), FN(xrEndSession), FN(xrRequestExitSession), FN(xrWaitFrame),
        FN(xrBeginFrame), FN(xrEndFrame), FN(xrPollEvent),
        FN(xrCreateReferenceSpace), FN(xrCreateActionSpace), FN(xrDestroySpace), FN(xrLocateSpace),
        FN(xrSyncActions), FN(xrGetActionStatePose), FN(xrGetCurrentInteractionProfile),
        FN(xrEnumerateBoundSourcesForAction), FN(xrGetInputSourceLocalizedName),
#ifdef _WIN32
        FN(xrConvertWin32PerformanceCounterToTimeKHR),
#else
        FN(xrConvertTimespecTimeToTimeKHR),
#endif
    };

    XrResult XRAPI_CALL rt_xrGetInstanceProcAddr(XrInstance, const char* name, PFN_xrVoidFunction* fn) {
        if (!std::strcmp(name, "xrGetInstanceProcAddr")) {
            *fn = reinterpret_cast<PFN_xrVoidFunction>(rt_xrGetInstanceProcAddr);
            return XR_SUCCESS;
        }
        auto it = kFunctions.find(name);
        *fn = it == kFunctions.end() ? nullptr : it->second;
        return *fn ? XR_SUCCESS : XR_ERROR_FUNCTION_UNSUPPORTED;
    }

} // namespace

RT_EXPORT XrResult XRAPI_CALL xrNegotiateLoaderRuntimeInterface(const XrNegotiateLoaderInfo* info,
                                                                XrNegotiateRuntimeRequest* req) {
    if (!info || !req)
        return XR_ERROR_INITIALIZATION_FAILED;
    req->runtimeInterfaceVersion = XR_CURRENT_LOADER_RUNTIME_VERSION;
    req->runtimeApiVersion = XR_API_VERSION_1_0;
    req->getInstanceProcAddr = rt_xrGetInstanceProcAddr;
    return XR_SUCCESS;
}
