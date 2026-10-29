// Catches the headset as its own driver registers it, so eye tracking can be attached to an
// HMD that belongs to another driver (Index, Beyond, Pimax, Quest via Steam Link / VD, ...).
#pragma once

#include <cstdint>
#include <functional>

#include <openvr_driver.h>

namespace etvr::shim {

    // Called on the HMD's driver thread right after the HMD's own Activate() succeeds.
    using HmdActivated = std::function<void(uint32_t deviceIndex)>;
    using HmdDeactivated = std::function<void()>;

    // Patch IVRServerDriverHost::TrackedDeviceAdded. SteamVR gives every driver a host object of
    // the same class, so patching the shared vtable also sees other drivers' devices.
    bool install(vr::IVRServerDriverHost* host, HmdActivated onActivated, HmdDeactivated onDeactivated);
    void uninstall();

} // namespace etvr::shim
