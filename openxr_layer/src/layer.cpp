// XR_APILAYER_EYETRACKVR_eye_gaze: adds XR_EXT_eye_gaze_interaction to OpenXR runtimes that
// don't have it (Monado, WiVRn, Virtual Desktop's VDXR, WMR, ...), fed by EyeTrackVR's gaze
// shared memory (sdk/eyetrackvr_gaze.h). Portable: no graphics API, no hooking library.
//
// It stays out of the way unless the app enables XR_EXT_eye_gaze_interaction and the runtime
// below doesn't already offer it. Then it:
//   - hides the extension from the runtime and answers supportsEyeGazeInteraction itself,
//   - takes the /interaction_profiles/ext/eye_gaze_interaction bindings and the /user/eyes_ext
//     subaction path, which the runtime would reject,
//   - locates gaze pose action spaces as  head (VIEW) pose * gaze rotation * poseInActionSpace.
//
// One instance at a time is served; a second concurrent instance is passed straight through.

#include <algorithm>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <unknwn.h>
#define XR_USE_PLATFORM_WIN32
#else
#include <time.h>
#define XR_USE_TIMESPEC
#endif

#include <openxr/openxr.h>
#include <openxr/openxr_loader_negotiation.h>
#include <openxr/openxr_platform.h>

#include "gaze_source.h"

#if defined(_WIN32)
#define LAYER_EXPORT extern "C" __declspec(dllexport)
#else
#define LAYER_EXPORT extern "C" __attribute__((visibility("default")))
#endif

namespace {

    constexpr const char* kLayerName = "XR_APILAYER_EYETRACKVR_eye_gaze";
    constexpr const char* kProfile = "/interaction_profiles/ext/eye_gaze_interaction";
    constexpr const char* kUserPath = "/user/eyes_ext";
    constexpr const char* kGazePose = "/user/eyes_ext/input/gaze_ext/pose";
    constexpr const char* kGazeComponent = "/user/eyes_ext/input/gaze_ext"; // accepted for leniency
#ifdef _WIN32
    constexpr const char* kTimeExtension = XR_KHR_WIN32_CONVERT_PERFORMANCE_COUNTER_TIME_EXTENSION_NAME;
#else
    constexpr const char* kTimeExtension = XR_KHR_CONVERT_TIMESPEC_TIME_EXTENSION_NAME;
#endif

    void Log(const char* fmt, ...) {
        static const bool quiet = std::getenv("ETVR_GAZE_LAYER_QUIET") != nullptr;
        if (quiet)
            return;
        char buffer[512];
        va_list args;
        va_start(args, fmt);
        std::vsnprintf(buffer, sizeof(buffer), fmt, args);
        va_end(args);
        std::fprintf(stderr, "[%s] %s\n", kLayerName, buffer);
#ifdef _WIN32
        OutputDebugStringA(buffer);
#endif
    }

    // ------------------------------------------------------------------ math

    XrQuaternionf mul(const XrQuaternionf& a, const XrQuaternionf& b) {
        return {a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
                a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
                a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
                a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z};
    }
    XrQuaternionf conj(const XrQuaternionf& q) {
        return {-q.x, -q.y, -q.z, q.w};
    }
    XrVector3f rotate(const XrQuaternionf& q, const XrVector3f& v) {
        const XrQuaternionf p = mul(mul(q, {v.x, v.y, v.z, 0.f}), conj(q));
        return {p.x, p.y, p.z};
    }
    XrPosef compose(const XrPosef& a, const XrPosef& b) { // a * b: b expressed in a
        const XrVector3f t = rotate(a.orientation, b.position);
        return {mul(a.orientation, b.orientation), {a.position.x + t.x, a.position.y + t.y, a.position.z + t.z}};
    }
    XrPosef invert(const XrPosef& p) {
        const XrQuaternionf q = conj(p.orientation);
        const XrVector3f t = rotate(q, p.position);
        return {q, {-t.x, -t.y, -t.z}};
    }
    // Rotation taking OpenXR forward (-Z) onto unit direction d.
    XrQuaternionf lookRotation(const float d[3]) {
        // a = (0,0,-1); axis = a x d = (d.y, -d.x, 0); w = 1 + a.d = 1 - d.z
        const float w = 1.f - d[2];
        if (w < 1e-6f)
            return {0.f, 1.f, 0.f, 0.f}; // looking straight back: 180 deg about Y
        const float x = d[1], y = -d[0];
        const float n = std::sqrt(x * x + y * y + w * w);
        return {x / n, y / n, 0.f, w / n};
    }
    constexpr XrPosef kIdentity{{0.f, 0.f, 0.f, 1.f}, {0.f, 0.f, 0.f}};

    // ------------------------------------------------------------------ state

    struct Next {
        PFN_xrGetInstanceProcAddr GetInstanceProcAddr{};
        PFN_xrDestroyInstance DestroyInstance{};
        PFN_xrGetSystemProperties GetSystemProperties{};
        PFN_xrStringToPath StringToPath{};
        PFN_xrPathToString PathToString{};
        PFN_xrCreateAction CreateAction{};
        PFN_xrDestroyAction DestroyAction{};
        PFN_xrSuggestInteractionProfileBindings SuggestInteractionProfileBindings{};
        PFN_xrCreateSession CreateSession{};
        PFN_xrDestroySession DestroySession{};
        PFN_xrCreateReferenceSpace CreateReferenceSpace{};
        PFN_xrCreateActionSpace CreateActionSpace{};
        PFN_xrDestroySpace DestroySpace{};
        PFN_xrLocateSpace LocateSpace{};
        PFN_xrLocateSpaces LocateSpaces{};       // OpenXR 1.1, may be absent
        PFN_xrLocateSpacesKHR LocateSpacesKHR{}; // XR_KHR_locate_spaces, may be absent
        PFN_xrGetActionStatePose GetActionStatePose{};
        PFN_xrGetCurrentInteractionProfile GetCurrentInteractionProfile{};
        PFN_xrEnumerateBoundSourcesForAction EnumerateBoundSourcesForAction{};
        PFN_xrGetInputSourceLocalizedName GetInputSourceLocalizedName{};
#ifdef _WIN32
        PFN_xrConvertWin32PerformanceCounterToTimeKHR ConvertTime{};
#else
        PFN_xrConvertTimespecTimeToTimeKHR ConvertTime{};
#endif
    };

    struct GazeSpace {
        XrSession session;
        XrPosef poseInActionSpace;
    };

    struct InstanceState {
        XrInstance instance{XR_NULL_HANDLE};
        Next next;
        XrPath profile{}, userPath{}, gazePose{}, gazeComponent{};
        std::unordered_set<XrAction> gazeActions;            // bound through the eye gaze profile
        std::unordered_set<XrAction> eyesSubactionActions;   // created with /user/eyes_ext
        std::unordered_map<XrSpace, std::pair<XrAction, XrPosef>> actionSpaces;
        std::unordered_map<XrSession, XrSpace> viewSpaces;
        std::unordered_map<XrSpace, XrSession> spaceSessions;
        etvr::GazeSource gaze;
#ifdef _WIN32
        int64_t qpcFrequency{1};
#endif
    };

    std::mutex g_mutex;
    InstanceState* g_state = nullptr; // the one served instance
    std::unordered_map<XrInstance, PFN_xrGetInstanceProcAddr> g_passthrough;

    template <typename T>
    void load(PFN_xrGetInstanceProcAddr gipa, XrInstance instance, const char* name, T& fn) {
        PFN_xrVoidFunction f = nullptr;
        if (XR_SUCCEEDED(gipa(instance, name, &f)))
            fn = reinterpret_cast<T>(f);
    }

    bool isGazeAction(InstanceState& s, XrAction action) {
        return s.gazeActions.count(action) != 0;
    }

    // EyeTrackVR's camera capture time as an XrTime, or 0 if the runtime can't convert times.
    XrTime sampleXrTime(InstanceState& s, int64_t sampleTimeNs) {
        XrTime time = 0;
        if (!s.next.ConvertTime)
            return 0;
#ifdef _WIN32
        LARGE_INTEGER counter;
        counter.QuadPart = (sampleTimeNs / 1'000'000'000LL) * s.qpcFrequency +
                           (sampleTimeNs % 1'000'000'000LL) * s.qpcFrequency / 1'000'000'000LL;
        if (XR_FAILED(s.next.ConvertTime(s.instance, &counter, &time)))
            return 0;
#else
        const timespec ts{time_t(sampleTimeNs / 1'000'000'000LL), long(sampleTimeNs % 1'000'000'000LL)};
        if (XR_FAILED(s.next.ConvertTime(s.instance, &ts, &time)))
            return 0;
#endif
        return time;
    }

    // Location of `space` relative to the session's VIEW space. Gaze spaces are computed (the
    // gaze ray starts between the eyes, the VIEW origin); anything else asks the runtime.
    // Returns the location flags (0 = not locatable).
    XrSpaceLocationFlags locateInView(InstanceState& s, XrSpace space, XrSpace view, XrTime time, XrPosef& out,
                                      XrTime* sampleTime) {
        auto it = s.actionSpaces.find(space);
        if (it != s.actionSpaces.end() && isGazeAction(s, it->second.first)) {
            etvr_gaze gaze;
            if (!s.gaze.read(gaze))
                return 0;
            if (sampleTime)
                *sampleTime = sampleXrTime(s, gaze.sample_time_ns);
            const XrPosef gazePose{lookRotation(gaze.eyes[ETVR_GAZE_EYE_COMBINED].direction), {0.f, 0.f, 0.f}};
            out = compose(gazePose, it->second.second);
            return XR_SPACE_LOCATION_ORIENTATION_VALID_BIT | XR_SPACE_LOCATION_ORIENTATION_TRACKED_BIT |
                   XR_SPACE_LOCATION_POSITION_VALID_BIT | XR_SPACE_LOCATION_POSITION_TRACKED_BIT;
        }
        XrSpaceLocation loc{XR_TYPE_SPACE_LOCATION};
        if (XR_FAILED(s.next.LocateSpace(space, view, time, &loc)))
            return 0;
        out = loc.pose;
        return loc.locationFlags;
    }

    bool involvesGaze(InstanceState& s, XrSpace space) {
        auto it = s.actionSpaces.find(space);
        return it != s.actionSpaces.end() && isGazeAction(s, it->second.first);
    }

    XrSession sessionOf(InstanceState& s, XrSpace space) {
        auto it = s.spaceSessions.find(space);
        return it == s.spaceSessions.end() ? XR_NULL_HANDLE : it->second;
    }

    // Shared by xrLocateSpace and xrLocateSpaces when a gaze space is involved.
    XrResult locateWithGaze(InstanceState& s, XrSpace space, XrSpace base, XrTime time, XrSpaceLocation* location) {
        const XrSession session = sessionOf(s, involvesGaze(s, space) ? space : base);
        auto view = s.viewSpaces.find(session);
        if (view == s.viewSpaces.end())
            return XR_ERROR_HANDLE_INVALID;
        XrTime sampleTime = 0;
        XrPosef spaceInView, baseInView;
        const XrSpaceLocationFlags a = locateInView(s, space, view->second, time, spaceInView, &sampleTime);
        const XrSpaceLocationFlags b = locateInView(s, base, view->second, time, baseInView, nullptr);
        location->locationFlags = 0;
        location->pose = kIdentity;
        if ((a & XR_SPACE_LOCATION_ORIENTATION_VALID_BIT) && (b & XR_SPACE_LOCATION_ORIENTATION_VALID_BIT)) {
            location->pose = compose(invert(baseInView), spaceInView);
            location->locationFlags = a & b;
        }
        for (auto* p = static_cast<XrBaseOutStructure*>(location->next); p; p = p->next) {
            if (p->type == XR_TYPE_EYE_GAZE_SAMPLE_TIME_EXT)
                reinterpret_cast<XrEyeGazeSampleTimeEXT*>(p)->time = location->locationFlags ? (sampleTime ? sampleTime : time) : 0;
            else if (p->type == XR_TYPE_SPACE_VELOCITY)
                reinterpret_cast<XrSpaceVelocity*>(p)->velocityFlags = 0; // not provided for gaze
        }
        return XR_SUCCESS;
    }

    // ------------------------------------------------------------------ hooks

#define STATE_OR(fallback)                                                                                         \
    std::lock_guard lock(g_mutex);                                                                                 \
    if (!g_state)                                                                                                  \
        return fallback;                                                                                           \
    InstanceState& s = *g_state

    XrResult XRAPI_CALL hook_xrDestroyInstance(XrInstance instance) {
        PFN_xrDestroyInstance destroy;
        {
            std::lock_guard lock(g_mutex);
            if (!g_state || g_state->instance != instance)
                return XR_ERROR_HANDLE_INVALID;
            destroy = g_state->next.DestroyInstance;
            delete g_state;
            g_state = nullptr;
        }
        Log("instance destroyed");
        return destroy(instance);
    }

    XrResult XRAPI_CALL hook_xrGetSystemProperties(XrInstance instance, XrSystemId system, XrSystemProperties* props) {
        STATE_OR(XR_ERROR_HANDLE_INVALID);
        // Take our struct out of the chain: the runtime doesn't know the extension.
        XrSystemEyeGazeInteractionPropertiesEXT* eye = nullptr;
        XrBaseOutStructure* before = nullptr;
        for (auto* p = reinterpret_cast<XrBaseOutStructure*>(props); p && p->next; p = p->next) {
            if (p->next->type == XR_TYPE_SYSTEM_EYE_GAZE_INTERACTION_PROPERTIES_EXT) {
                before = p;
                eye = reinterpret_cast<XrSystemEyeGazeInteractionPropertiesEXT*>(p->next);
                p->next = p->next->next;
                break;
            }
        }
        const XrResult result = s.next.GetSystemProperties(instance, system, props);
        if (eye) {
            before->next = reinterpret_cast<XrBaseOutStructure*>(eye);
            // Only while EyeTrackVR publishes gaze, so apps without it keep their usual path.
            eye->supportsEyeGazeInteraction = s.gaze.published() ? XR_TRUE : XR_FALSE;
            Log("supportsEyeGazeInteraction = %d", int(eye->supportsEyeGazeInteraction));
        }
        return result;
    }

    XrResult XRAPI_CALL hook_xrCreateAction(XrActionSet set, const XrActionCreateInfo* info, XrAction* action) {
        STATE_OR(XR_ERROR_HANDLE_INVALID);
        if (!info || !info->subactionPaths)
            return s.next.CreateAction(set, info, action);
        // The runtime would reject /user/eyes_ext as a top level path.
        std::vector<XrPath> kept;
        bool hadEyes = false;
        for (uint32_t i = 0; i < info->countSubactionPaths; i++) {
            if (info->subactionPaths[i] == s.userPath)
                hadEyes = true;
            else
                kept.push_back(info->subactionPaths[i]);
        }
        if (!hadEyes)
            return s.next.CreateAction(set, info, action);
        XrActionCreateInfo copy = *info;
        copy.countSubactionPaths = uint32_t(kept.size());
        copy.subactionPaths = kept.empty() ? nullptr : kept.data();
        const XrResult result = s.next.CreateAction(set, &copy, action);
        if (XR_SUCCEEDED(result))
            s.eyesSubactionActions.insert(*action);
        return result;
    }

    XrResult XRAPI_CALL hook_xrDestroyAction(XrAction action) {
        STATE_OR(XR_ERROR_HANDLE_INVALID);
        s.gazeActions.erase(action);
        s.eyesSubactionActions.erase(action);
        return s.next.DestroyAction(action);
    }

    XrResult XRAPI_CALL hook_xrSuggestInteractionProfileBindings(XrInstance instance,
                                                                 const XrInteractionProfileSuggestedBinding* suggested) {
        STATE_OR(XR_ERROR_HANDLE_INVALID);
        if (!suggested || suggested->interactionProfile != s.profile)
            return s.next.SuggestInteractionProfileBindings(instance, suggested);
        std::unordered_set<XrAction> actions;
        for (uint32_t i = 0; i < suggested->countSuggestedBindings; i++) {
            const XrActionSuggestedBinding& b = suggested->suggestedBindings[i];
            if (b.binding != s.gazePose && b.binding != s.gazeComponent)
                return XR_ERROR_PATH_UNSUPPORTED;
            actions.insert(b.action);
        }
        // A later suggestion for the same profile replaces the earlier one.
        s.gazeActions = std::move(actions);
        Log("eye gaze bindings: %zu action(s)", s.gazeActions.size());
        return XR_SUCCESS;
    }

    XrResult XRAPI_CALL hook_xrCreateSession(XrInstance instance, const XrSessionCreateInfo* info, XrSession* session) {
        STATE_OR(XR_ERROR_HANDLE_INVALID);
        const XrResult result = s.next.CreateSession(instance, info, session);
        if (XR_FAILED(result))
            return result;
        XrReferenceSpaceCreateInfo view{XR_TYPE_REFERENCE_SPACE_CREATE_INFO};
        view.referenceSpaceType = XR_REFERENCE_SPACE_TYPE_VIEW;
        view.poseInReferenceSpace = kIdentity;
        XrSpace space = XR_NULL_HANDLE;
        if (XR_SUCCEEDED(s.next.CreateReferenceSpace(*session, &view, &space))) {
            s.viewSpaces[*session] = space;
            s.spaceSessions[space] = *session;
        } else {
            Log("could not create a VIEW space; gaze unavailable for this session");
        }
        return result;
    }

    XrResult XRAPI_CALL hook_xrDestroySession(XrSession session) {
        STATE_OR(XR_ERROR_HANDLE_INVALID);
        auto view = s.viewSpaces.find(session);
        if (view != s.viewSpaces.end()) {
            s.next.DestroySpace(view->second);
            s.viewSpaces.erase(view);
        }
        for (auto it = s.spaceSessions.begin(); it != s.spaceSessions.end();) {
            if (it->second == session) {
                s.actionSpaces.erase(it->first);
                it = s.spaceSessions.erase(it);
            } else {
                ++it;
            }
        }
        return s.next.DestroySession(session);
    }

    XrResult XRAPI_CALL hook_xrCreateReferenceSpace(XrSession session, const XrReferenceSpaceCreateInfo* info, XrSpace* space) {
        STATE_OR(XR_ERROR_HANDLE_INVALID);
        const XrResult result = s.next.CreateReferenceSpace(session, info, space);
        if (XR_SUCCEEDED(result))
            s.spaceSessions[*space] = session;
        return result;
    }

    XrResult XRAPI_CALL hook_xrCreateActionSpace(XrSession session, const XrActionSpaceCreateInfo* info, XrSpace* space) {
        STATE_OR(XR_ERROR_HANDLE_INVALID);
        if (!info)
            return s.next.CreateActionSpace(session, info, space);
        XrActionSpaceCreateInfo copy = *info;
        if (copy.subactionPath == s.userPath)
            copy.subactionPath = XR_NULL_PATH; // stripped at xrCreateAction too
        const XrResult result = s.next.CreateActionSpace(session, &copy, space);
        if (XR_SUCCEEDED(result)) {
            // Bindings may be suggested after the space exists, so remember every action space.
            s.actionSpaces[*space] = {info->action, info->poseInActionSpace};
            s.spaceSessions[*space] = session;
        }
        return result;
    }

    XrResult XRAPI_CALL hook_xrDestroySpace(XrSpace space) {
        STATE_OR(XR_ERROR_HANDLE_INVALID);
        s.actionSpaces.erase(space);
        s.spaceSessions.erase(space);
        return s.next.DestroySpace(space);
    }

    XrResult XRAPI_CALL hook_xrLocateSpace(XrSpace space, XrSpace base, XrTime time, XrSpaceLocation* location) {
        STATE_OR(XR_ERROR_HANDLE_INVALID);
        if (!location || !(involvesGaze(s, space) || involvesGaze(s, base)))
            return s.next.LocateSpace(space, base, time, location);
        return locateWithGaze(s, space, base, time, location);
    }

    // xrLocateSpaces (1.1) and xrLocateSpacesKHR share a signature; `forward` is the runtime's.
    XrResult locateMany(InstanceState& s, XrSession session, const XrSpacesLocateInfo* info, XrSpaceLocations* out,
                        PFN_xrLocateSpaces forward) {
        if (!info || !out)
            return forward(session, info, out);
        bool gaze = involvesGaze(s, info->baseSpace);
        for (uint32_t i = 0; i < info->spaceCount && !gaze; i++)
            gaze = involvesGaze(s, info->spaces[i]);
        if (!gaze)
            return forward(session, info, out);
        if (out->locationCount != info->spaceCount)
            return XR_ERROR_VALIDATION_FAILURE;
        XrSpaceVelocities* velocities = nullptr;
        for (auto* p = static_cast<XrBaseOutStructure*>(out->next); p; p = p->next)
            if (p->type == XR_TYPE_SPACE_VELOCITIES)
                velocities = reinterpret_cast<XrSpaceVelocities*>(p);
        for (uint32_t i = 0; i < info->spaceCount; i++) {
            XrSpaceVelocity velocity{XR_TYPE_SPACE_VELOCITY};
            XrSpaceLocation loc{XR_TYPE_SPACE_LOCATION, velocities ? &velocity : nullptr};
            const XrResult r = (involvesGaze(s, info->spaces[i]) || involvesGaze(s, info->baseSpace))
                                   ? locateWithGaze(s, info->spaces[i], info->baseSpace, info->time, &loc)
                                   : s.next.LocateSpace(info->spaces[i], info->baseSpace, info->time, &loc);
            if (XR_FAILED(r))
                return r;
            out->locations[i] = {loc.locationFlags, loc.pose};
            if (velocities && i < velocities->velocityCount)
                velocities->velocities[i] = {velocity.velocityFlags, velocity.linearVelocity, velocity.angularVelocity};
        }
        return XR_SUCCESS;
    }

    XrResult XRAPI_CALL hook_xrLocateSpaces(XrSession session, const XrSpacesLocateInfo* info, XrSpaceLocations* out) {
        STATE_OR(XR_ERROR_HANDLE_INVALID);
        return locateMany(s, session, info, out, s.next.LocateSpaces);
    }

    XrResult XRAPI_CALL hook_xrLocateSpacesKHR(XrSession session, const XrSpacesLocateInfo* info, XrSpaceLocations* out) {
        STATE_OR(XR_ERROR_HANDLE_INVALID);
        return locateMany(s, session, info, out, s.next.LocateSpacesKHR);
    }

    XrResult XRAPI_CALL hook_xrGetActionStatePose(XrSession session, const XrActionStateGetInfo* info, XrActionStatePose* state) {
        STATE_OR(XR_ERROR_HANDLE_INVALID);
        if (!info || !state)
            return s.next.GetActionStatePose(session, info, state);
        XrActionStateGetInfo copy = *info;
        const bool eyesSubaction = copy.subactionPath == s.userPath;
        if (eyesSubaction)
            copy.subactionPath = XR_NULL_PATH;
        const XrResult result = s.next.GetActionStatePose(session, &copy, state);
        if (XR_SUCCEEDED(result) && isGazeAction(s, info->action) &&
            (info->subactionPath == XR_NULL_PATH || eyesSubaction)) {
            // Active while EyeTrackVR has gaze; otherwise whatever the runtime said for the
            // action's other bindings (if it has any).
            etvr_gaze gaze;
            if (s.gaze.read(gaze))
                state->isActive = XR_TRUE;
            else if (eyesSubaction)
                state->isActive = XR_FALSE;
        }
        return result;
    }

    XrResult XRAPI_CALL hook_xrGetCurrentInteractionProfile(XrSession session, XrPath topLevelUserPath,
                                                           XrInteractionProfileState* state) {
        STATE_OR(XR_ERROR_HANDLE_INVALID);
        if (topLevelUserPath != s.userPath || !state)
            return s.next.GetCurrentInteractionProfile(session, topLevelUserPath, state);
        state->interactionProfile = s.gazeActions.empty() ? XR_NULL_PATH : s.profile;
        return XR_SUCCESS;
    }

    XrResult XRAPI_CALL hook_xrEnumerateBoundSourcesForAction(XrSession session,
                                                             const XrBoundSourcesForActionEnumerateInfo* info,
                                                             uint32_t capacity, uint32_t* count, XrPath* sources) {
        STATE_OR(XR_ERROR_HANDLE_INVALID);
        if (!info || !count || !isGazeAction(s, info->action))
            return s.next.EnumerateBoundSourcesForAction(session, info, capacity, count, sources);
        uint32_t runtimeCount = 0;
        XrResult result = s.next.EnumerateBoundSourcesForAction(session, info, 0, &runtimeCount, nullptr);
        if (XR_FAILED(result))
            return result;
        std::vector<XrPath> all(runtimeCount);
        if (runtimeCount)
            s.next.EnumerateBoundSourcesForAction(session, info, runtimeCount, &runtimeCount, all.data());
        all.resize(runtimeCount);
        all.push_back(s.gazePose);
        *count = uint32_t(all.size());
        if (capacity == 0)
            return XR_SUCCESS;
        if (capacity < all.size())
            return XR_ERROR_SIZE_INSUFFICIENT;
        std::copy(all.begin(), all.end(), sources);
        return XR_SUCCESS;
    }

    XrResult XRAPI_CALL hook_xrGetInputSourceLocalizedName(XrSession session, const XrInputSourceLocalizedNameGetInfo* info,
                                                          uint32_t capacity, uint32_t* count, char* buffer) {
        STATE_OR(XR_ERROR_HANDLE_INVALID);
        if (!info || !count || info->sourcePath != s.gazePose)
            return s.next.GetInputSourceLocalizedName(session, info, capacity, count, buffer);
        std::string name;
        if (info->whichComponents & XR_INPUT_SOURCE_LOCALIZED_NAME_USER_PATH_BIT)
            name += "Eyes ";
        if (info->whichComponents & XR_INPUT_SOURCE_LOCALIZED_NAME_INTERACTION_PROFILE_BIT)
            name += "EyeTrackVR Eye Tracker ";
        if (info->whichComponents & XR_INPUT_SOURCE_LOCALIZED_NAME_COMPONENT_BIT)
            name += "Gaze ";
        if (!name.empty())
            name.pop_back();
        *count = uint32_t(name.size() + 1);
        if (capacity == 0)
            return XR_SUCCESS;
        if (capacity < *count)
            return XR_ERROR_SIZE_INSUFFICIENT;
        std::memcpy(buffer, name.c_str(), *count);
        return XR_SUCCESS;
    }

    struct Hook {
        const char* name;
        PFN_xrVoidFunction fn;
    };
#define HOOK(f) {#f, reinterpret_cast<PFN_xrVoidFunction>(hook_##f)}
    const Hook kHooks[] = {
        HOOK(xrDestroyInstance),
        HOOK(xrGetSystemProperties),
        HOOK(xrCreateAction),
        HOOK(xrDestroyAction),
        HOOK(xrSuggestInteractionProfileBindings),
        HOOK(xrCreateSession),
        HOOK(xrDestroySession),
        HOOK(xrCreateReferenceSpace),
        HOOK(xrCreateActionSpace),
        HOOK(xrDestroySpace),
        HOOK(xrLocateSpace),
        HOOK(xrLocateSpaces),
        HOOK(xrLocateSpacesKHR),
        HOOK(xrGetActionStatePose),
        HOOK(xrGetCurrentInteractionProfile),
        HOOK(xrEnumerateBoundSourcesForAction),
        HOOK(xrGetInputSourceLocalizedName),
    };

    XrResult XRAPI_CALL layer_xrGetInstanceProcAddr(XrInstance instance, const char* name, PFN_xrVoidFunction* function) {
        PFN_xrGetInstanceProcAddr next = nullptr;
        bool served = false;
        {
            std::lock_guard lock(g_mutex);
            if (g_state && g_state->instance == instance) {
                next = g_state->next.GetInstanceProcAddr;
                served = true;
            } else if (auto it = g_passthrough.find(instance); it != g_passthrough.end()) {
                next = it->second;
            }
        }
        if (!next)
            return XR_ERROR_HANDLE_INVALID;
        const XrResult result = next(instance, name, function);
        if (!served || XR_FAILED(result))
            return result;
        for (const Hook& h : kHooks) {
            if (!std::strcmp(name, h.name)) {
                *function = h.fn;
                break;
            }
        }
        return result;
    }

    bool runtimeHasExtension(PFN_xrGetInstanceProcAddr gipa, const char* extension) {
        PFN_xrEnumerateInstanceExtensionProperties enumerate = nullptr;
        load(gipa, XR_NULL_HANDLE, "xrEnumerateInstanceExtensionProperties", enumerate);
        if (!enumerate)
            return false;
        uint32_t count = 0;
        if (XR_FAILED(enumerate(nullptr, 0, &count, nullptr)))
            return false;
        std::vector<XrExtensionProperties> props(count, {XR_TYPE_EXTENSION_PROPERTIES});
        if (XR_FAILED(enumerate(nullptr, count, &count, props.data())))
            return false;
        return std::any_of(props.begin(), props.begin() + count,
                           [&](const XrExtensionProperties& p) { return !std::strcmp(p.extensionName, extension); });
    }

    XrResult XRAPI_CALL layer_xrCreateApiLayerInstance(const XrInstanceCreateInfo* info,
                                                       const XrApiLayerCreateInfo* layerInfo,
                                                       XrInstance* instance) {
        if (!layerInfo || !layerInfo->nextInfo)
            return XR_ERROR_INITIALIZATION_FAILED;
        PFN_xrGetInstanceProcAddr nextGipa = layerInfo->nextInfo->nextGetInstanceProcAddr;

        // Hand the next layer (or the runtime) the rest of the chain.
        XrApiLayerCreateInfo nextLayerInfo = *layerInfo;
        nextLayerInfo.nextInfo = layerInfo->nextInfo->next;

        bool appWantsGaze = false;
        for (uint32_t i = 0; i < info->enabledExtensionCount; i++)
            appWantsGaze |= !std::strcmp(info->enabledExtensionNames[i], XR_EXT_EYE_GAZE_INTERACTION_EXTENSION_NAME);
        const bool force = std::getenv("ETVR_GAZE_LAYER_FORCE") != nullptr;
        const bool runtimeHasGaze = runtimeHasExtension(nextGipa, XR_EXT_EYE_GAZE_INTERACTION_EXTENSION_NAME);
        bool serve = appWantsGaze && (!runtimeHasGaze || force);
        {
            std::lock_guard lock(g_mutex);
            if (serve && g_state) {
                Log("another instance is already served; passing this one through");
                serve = false;
            }
        }

        if (!serve) {
            const XrResult result = layerInfo->nextInfo->nextCreateApiLayerInstance(info, &nextLayerInfo, instance);
            if (XR_SUCCEEDED(result)) {
                std::lock_guard lock(g_mutex);
                g_passthrough[*instance] = nextGipa;
            }
            Log("pass-through (%s)", !appWantsGaze ? "app does not use eye gaze"
                                     : runtimeHasGaze ? "runtime has eye gaze; set ETVR_GAZE_LAYER_FORCE=1 to override"
                                                      : "second instance");
            return result;
        }

        // Enabled extensions as the runtime should see them: without eye gaze, with time conversion.
        std::vector<const char*> extensions;
        bool timeEnabled = false;
        for (uint32_t i = 0; i < info->enabledExtensionCount; i++) {
            const char* e = info->enabledExtensionNames[i];
            if (!std::strcmp(e, XR_EXT_EYE_GAZE_INTERACTION_EXTENSION_NAME) && !runtimeHasGaze)
                continue;
            timeEnabled |= !std::strcmp(e, kTimeExtension);
            extensions.push_back(e);
        }
        const bool timeAvailable = timeEnabled || runtimeHasExtension(nextGipa, kTimeExtension);
        if (timeAvailable && !timeEnabled)
            extensions.push_back(kTimeExtension);
        XrInstanceCreateInfo copy = *info;
        copy.enabledExtensionCount = uint32_t(extensions.size());
        copy.enabledExtensionNames = extensions.data();

        const XrResult result = layerInfo->nextInfo->nextCreateApiLayerInstance(&copy, &nextLayerInfo, instance);
        if (XR_FAILED(result))
            return result;

        auto* s = new InstanceState;
        s->instance = *instance;
        Next& n = s->next;
        n.GetInstanceProcAddr = nextGipa;
        load(nextGipa, *instance, "xrDestroyInstance", n.DestroyInstance);
        load(nextGipa, *instance, "xrGetSystemProperties", n.GetSystemProperties);
        load(nextGipa, *instance, "xrStringToPath", n.StringToPath);
        load(nextGipa, *instance, "xrPathToString", n.PathToString);
        load(nextGipa, *instance, "xrCreateAction", n.CreateAction);
        load(nextGipa, *instance, "xrDestroyAction", n.DestroyAction);
        load(nextGipa, *instance, "xrSuggestInteractionProfileBindings", n.SuggestInteractionProfileBindings);
        load(nextGipa, *instance, "xrCreateSession", n.CreateSession);
        load(nextGipa, *instance, "xrDestroySession", n.DestroySession);
        load(nextGipa, *instance, "xrCreateReferenceSpace", n.CreateReferenceSpace);
        load(nextGipa, *instance, "xrCreateActionSpace", n.CreateActionSpace);
        load(nextGipa, *instance, "xrDestroySpace", n.DestroySpace);
        load(nextGipa, *instance, "xrLocateSpace", n.LocateSpace);
        load(nextGipa, *instance, "xrLocateSpaces", n.LocateSpaces);
        load(nextGipa, *instance, "xrLocateSpacesKHR", n.LocateSpacesKHR);
        load(nextGipa, *instance, "xrGetActionStatePose", n.GetActionStatePose);
        load(nextGipa, *instance, "xrGetCurrentInteractionProfile", n.GetCurrentInteractionProfile);
        load(nextGipa, *instance, "xrEnumerateBoundSourcesForAction", n.EnumerateBoundSourcesForAction);
        load(nextGipa, *instance, "xrGetInputSourceLocalizedName", n.GetInputSourceLocalizedName);
        if (timeAvailable) {
#ifdef _WIN32
            load(nextGipa, *instance, "xrConvertWin32PerformanceCounterToTimeKHR", n.ConvertTime);
            LARGE_INTEGER frequency;
            QueryPerformanceFrequency(&frequency);
            s->qpcFrequency = frequency.QuadPart;
#else
            load(nextGipa, *instance, "xrConvertTimespecTimeToTimeKHR", n.ConvertTime);
#endif
        }
        n.StringToPath(*instance, kProfile, &s->profile);
        n.StringToPath(*instance, kUserPath, &s->userPath);
        n.StringToPath(*instance, kGazePose, &s->gazePose);
        n.StringToPath(*instance, kGazeComponent, &s->gazeComponent);

        std::lock_guard lock(g_mutex);
        g_state = s;
        Log("serving XR_EXT_eye_gaze_interaction from EyeTrackVR (gaze %s, sample times %s)",
            s->gaze.published() ? "published" : "not published yet", n.ConvertTime ? "converted" : "approximate");
        return result;
    }

} // namespace

LAYER_EXPORT XrResult XRAPI_CALL xrNegotiateLoaderApiLayerInterface(const XrNegotiateLoaderInfo* loaderInfo,
                                                                    const char* layerName,
                                                                    XrNegotiateApiLayerRequest* request) {
    if (!loaderInfo || !request || loaderInfo->structType != XR_LOADER_INTERFACE_STRUCT_LOADER_INFO ||
        request->structType != XR_LOADER_INTERFACE_STRUCT_API_LAYER_REQUEST ||
        loaderInfo->minInterfaceVersion > XR_CURRENT_LOADER_API_LAYER_VERSION ||
        loaderInfo->maxInterfaceVersion < XR_CURRENT_LOADER_API_LAYER_VERSION)
        return XR_ERROR_INITIALIZATION_FAILED;
    if (layerName && std::strcmp(layerName, kLayerName) != 0)
        return XR_ERROR_INITIALIZATION_FAILED;
    request->layerInterfaceVersion = XR_CURRENT_LOADER_API_LAYER_VERSION;
    // Works with OpenXR 1.0 and 1.1 apps; report the newest the loader accepts.
    request->layerApiVersion = std::min<XrVersion>(loaderInfo->maxApiVersion, XR_API_VERSION_1_1);
    request->getInstanceProcAddr = layer_xrGetInstanceProcAddr;
    request->createApiLayerInstance = layer_xrCreateApiLayerInstance;
    return XR_SUCCESS;
}
