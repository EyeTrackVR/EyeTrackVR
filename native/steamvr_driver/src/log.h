#pragma once

#include <cstdarg>
#include <cstdio>

#include <openvr_driver.h>

namespace etvr {

    // To vrserver.txt, prefixed with the driver name by SteamVR.
    inline void Log(const char* fmt, ...) {
        char buffer[1024];
        va_list args;
        va_start(args, fmt);
        vsnprintf(buffer, sizeof(buffer), fmt, args);
        va_end(args);
        if (vr::VRDriverLog())
            vr::VRDriverLog()->Log(buffer);
    }

} // namespace etvr
