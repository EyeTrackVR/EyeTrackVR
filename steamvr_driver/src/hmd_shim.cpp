#include "hmd_shim.h"

#include <atomic>
#include <cstdint>
#include <mutex>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#else
#include <sys/mman.h>
#include <unistd.h>
#endif

#include "log.h"

static_assert(sizeof(void*) == 8, "the vtable patch assumes a 64-bit ABI (x64 / arm64)");

namespace etvr::shim {

    namespace {
        // TrackedDeviceAdded is the first virtual of IVRServerDriverHost, which has no virtual
        // destructor, so it is slot 0 in both the MSVC and Itanium (Linux) vtable layouts. On
        // 64-bit both ABIs pass `this` as the first argument, so a free function can stand in.
        constexpr size_t kTrackedDeviceAddedSlot = 0;
        using TrackedDeviceAddedFn = bool (*)(vr::IVRServerDriverHost* self,
                                             const char* serial,
                                             vr::ETrackedDeviceClass deviceClass,
                                             vr::ITrackedDeviceServerDriver* driver);

        std::mutex g_mutex;
        void** g_vtable{nullptr};
        TrackedDeviceAddedFn g_original{nullptr};
        HmdActivated g_onActivated;
        HmdDeactivated g_onDeactivated;
        std::atomic<bool> g_wrapped{false};

        bool writeSlot(void** slot, void* value) {
#ifdef _WIN32
            DWORD old;
            if (!VirtualProtect(slot, sizeof(void*), PAGE_READWRITE, &old))
                return false;
            *slot = value;
            VirtualProtect(slot, sizeof(void*), old, &old);
            FlushInstructionCache(GetCurrentProcess(), slot, sizeof(void*));
            return true;
#else
            const uintptr_t page = uintptr_t(sysconf(_SC_PAGESIZE));
            void* start = reinterpret_cast<void*>(uintptr_t(slot) & ~(page - 1));
            // vtables live in read-only relocated data (RELRO). The page is left writable: its
            // original protection isn't known here, and read-only could break a neighbour.
            if (mprotect(start, page, PROT_READ | PROT_WRITE) != 0)
                return false;
            *slot = value;
            return true;
#endif
        }

        // Forwards everything to the HMD's real driver and reports activation.
        class HmdProxy final : public vr::ITrackedDeviceServerDriver {
          public:
            explicit HmdProxy(vr::ITrackedDeviceServerDriver* real) : m_real(real) {
            }

            vr::EVRInitError Activate(uint32_t unObjectId) override {
                const vr::EVRInitError result = m_real->Activate(unObjectId);
                if (result == vr::VRInitError_None && g_onActivated)
                    g_onActivated(unObjectId);
                return result;
            }
            void Deactivate() override {
                if (g_onDeactivated)
                    g_onDeactivated();
                m_real->Deactivate();
            }
            void EnterStandby() override {
                m_real->EnterStandby();
            }
            void* GetComponent(const char* pchComponentNameAndVersion) override {
                return m_real->GetComponent(pchComponentNameAndVersion);
            }
            void DebugRequest(const char* pchRequest, char* pchResponseBuffer, uint32_t unResponseBufferSize) override {
                m_real->DebugRequest(pchRequest, pchResponseBuffer, unResponseBufferSize);
            }
            vr::DriverPose_t GetPose() override {
                return m_real->GetPose();
            }

          private:
            vr::ITrackedDeviceServerDriver* m_real;
        };

        bool hookedTrackedDeviceAdded(vr::IVRServerDriverHost* self,
                                      const char* serial,
                                      vr::ETrackedDeviceClass deviceClass,
                                      vr::ITrackedDeviceServerDriver* driver) {
            if (deviceClass == vr::TrackedDeviceClass_HMD && driver && !g_wrapped.exchange(true)) {
                Log("Wrapping HMD '%s' to attach eye tracking", serial ? serial : "?");
                // Lives as long as vrserver: SteamVR keeps the device pointer until exit.
                driver = new HmdProxy(driver);
            }
            return g_original(self, serial, deviceClass, driver);
        }
    } // namespace

    bool install(vr::IVRServerDriverHost* host, HmdActivated onActivated, HmdDeactivated onDeactivated) {
        std::lock_guard lock(g_mutex);
        if (g_vtable)
            return true;
        void** vtable = *reinterpret_cast<void***>(host);
        void** slot = &vtable[kTrackedDeviceAddedSlot];
        g_onActivated = std::move(onActivated);
        g_onDeactivated = std::move(onDeactivated);
        g_original = reinterpret_cast<TrackedDeviceAddedFn>(*slot);
        if (!writeSlot(slot, reinterpret_cast<void*>(&hookedTrackedDeviceAdded))) {
            Log("Could not patch IVRServerDriverHost::TrackedDeviceAdded");
            g_original = nullptr;
            return false;
        }
        g_vtable = vtable;
        return true;
    }

    void uninstall() {
        std::lock_guard lock(g_mutex);
        if (!g_vtable)
            return;
        writeSlot(&g_vtable[kTrackedDeviceAddedSlot], reinterpret_cast<void*>(g_original));
        g_vtable = nullptr;
    }

} // namespace etvr::shim
