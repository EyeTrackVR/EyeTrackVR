// Reads EyeTrackVR's gaze shared memory (sdk/eyetrackvr_gaze.h) on Windows and Linux.
// Shared by the SteamVR driver and the OpenXR layer; usable by other C++ readers too.
#pragma once

#include <cstdint>

#include "eyetrackvr_gaze.h"

namespace etvr {

    class GazeSource {
      public:
        GazeSource();
        ~GazeSource();
        GazeSource(const GazeSource&) = delete;
        GazeSource& operator=(const GazeSource&) = delete;

        // A fresh, valid-combined-gaze sample, or false. Reopens the block as needed:
        // EyeTrackVR can start after SteamVR, and on Linux it recreates the block on restart.
        bool read(etvr_gaze& out);

        // The block exists (EyeTrackVR's "Foveated rendering gaze" output is on).
        bool published();

        // Now, in the clock domain the block's *_time_ns fields use on this OS.
        int64_t nowNs() const;

      private:
        bool open();
        void close();
        bool readRaw(etvr_gaze& out);

        const void* m_view{nullptr};
        void* m_handle{nullptr}; // Windows file mapping handle
        int64_t m_qpcFrequency{1};
        int64_t m_nextOpenNs{0};
        int64_t m_staleSinceNs{0};
        uint32_t m_expectedClock{0};
    };

} // namespace etvr
