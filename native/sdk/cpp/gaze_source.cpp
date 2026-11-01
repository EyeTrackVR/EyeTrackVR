#include "gaze_source.h"

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#endif

namespace etvr {

    namespace {
        constexpr int64_t kReopenIntervalNs = 1'000'000'000;  // look for the block once a second
        constexpr int64_t kReopenWhenStaleNs = 1'000'000'000; // a stale block may be an old, unlinked one
    } // namespace

    GazeSource::GazeSource() {
#ifdef _WIN32
        LARGE_INTEGER frequency;
        QueryPerformanceFrequency(&frequency);
        m_qpcFrequency = frequency.QuadPart;
        m_expectedClock = ETVR_GAZE_CLOCK_QPC_NS;
#else
        m_expectedClock = ETVR_GAZE_CLOCK_MONOTONIC_NS;
#endif
    }

    GazeSource::~GazeSource() {
        close();
    }

    int64_t GazeSource::nowNs() const {
#ifdef _WIN32
        // Same scaling as EyeTrackVR's time.perf_counter_ns().
        LARGE_INTEGER counter;
        QueryPerformanceCounter(&counter);
        return (counter.QuadPart / m_qpcFrequency) * 1'000'000'000LL +
               (counter.QuadPart % m_qpcFrequency) * 1'000'000'000LL / m_qpcFrequency;
#else
        timespec ts;
        clock_gettime(CLOCK_MONOTONIC, &ts);
        return int64_t(ts.tv_sec) * 1'000'000'000LL + ts.tv_nsec;
#endif
    }

    bool GazeSource::open() {
#ifdef _WIN32
        HANDLE mapping = OpenFileMappingW(FILE_MAP_READ, FALSE, ETVR_GAZE_WIN32_NAME);
        if (!mapping)
            return false;
        const void* view = MapViewOfFile(mapping, FILE_MAP_READ, 0, 0, ETVR_GAZE_SIZE);
        if (!view) {
            CloseHandle(mapping);
            return false;
        }
        m_handle = mapping;
        m_view = view;
#else
        // Same object as shm_open(ETVR_GAZE_POSIX_NAME), without needing glibc 2.34's libc shm_open.
        const int fd = ::open("/dev/shm" ETVR_GAZE_POSIX_NAME, O_RDONLY | O_CLOEXEC);
        if (fd < 0)
            return false;
        void* view = mmap(nullptr, ETVR_GAZE_SIZE, PROT_READ, MAP_SHARED, fd, 0);
        ::close(fd);
        if (view == MAP_FAILED)
            return false;
        m_view = view;
#endif
        m_staleSinceNs = 0;
        return true;
    }

    void GazeSource::close() {
        if (!m_view)
            return;
#ifdef _WIN32
        UnmapViewOfFile(m_view);
        CloseHandle(static_cast<HANDLE>(m_handle));
        m_handle = nullptr;
#else
        munmap(const_cast<void*>(m_view), ETVR_GAZE_SIZE);
#endif
        m_view = nullptr;
    }

    bool GazeSource::published() {
        const int64_t now = nowNs();
        if (!m_view && now >= m_nextOpenNs) {
            m_nextOpenNs = now + kReopenIntervalNs;
            open();
        }
        return m_view != nullptr;
    }

    bool GazeSource::readRaw(etvr_gaze& out) {
        // The writer holds the seqlock for well under a microsecond; a few retries are plenty.
        for (int retry = 0; retry < 8; retry++) {
            if (etvr_gaze_read(m_view, &out))
                return out.clock == m_expectedClock;
        }
        return false;
    }

    bool GazeSource::read(etvr_gaze& out) {
        if (!published())
            return false;
        const int64_t now = nowNs();
        if (readRaw(out) && etvr_gaze_usable(&out, now)) {
            m_staleSinceNs = 0;
            return true;
        }
        // Nothing fresh. EyeTrackVR may have quit (Windows keeps our mapping alive and it
        // reads "no gaze") or been restarted (Linux unlinks and recreates the block, so ours
        // is orphaned). Reopen after a while either way.
        if (!m_staleSinceNs)
            m_staleSinceNs = now;
        else if (now - m_staleSinceNs > kReopenWhenStaleNs) {
            close();
            m_nextOpenNs = 0;
        }
        return false;
    }

} // namespace etvr
