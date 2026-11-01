/*
 * EyeTrackVR gaze shared memory, version 1.
 *
 * EyeTrackVR publishes the latest eye gaze in a small shared memory block so
 * foveated rendering and streaming tools (OpenXR API layers, SteamVR drivers,
 * encoders) can read it without OSC parsing or a network hop. One writer
 * (EyeTrackVR), any number of readers. Readers never write.
 *
 *   Windows: named file mapping  "Local\EyeTrackVR.Gaze.v1"   (OpenFileMappingW)
 *   Linux:   POSIX shared memory "/eyetrackvr_gaze_v1"        (shm_open)
 *
 * The block exists only while EyeTrackVR's "Foveated rendering gaze" output is
 * on. A reader that cannot open it, or reads a stale or invalid sample, should
 * fall back to fixed foveation. See docs/gaze-shared-memory.md.
 *
 * Header-only, C99 / C++11. Copy this file into consumers as is.
 */

#ifndef EYETRACKVR_GAZE_H
#define EYETRACKVR_GAZE_H

#include <stdint.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

#define ETVR_GAZE_MAGIC "ETVG"
#define ETVR_GAZE_VERSION 1
#define ETVR_GAZE_SIZE 256
#define ETVR_GAZE_CRC_START 16
#define ETVR_GAZE_WIN32_NAME L"Local\\EyeTrackVR.Gaze.v1"
#define ETVR_GAZE_POSIX_NAME "/eyetrackvr_gaze_v1"

/* Clock domain of every *_time_ns field. Both are what the OpenXR
 * XR_KHR_win32_convert_performance_counter_time / XR_KHR_convert_timespec_time
 * extensions take, after converting ns back to the native unit. */
#define ETVR_GAZE_CLOCK_QPC_NS 1       /* QueryPerformanceCounter, scaled to ns */
#define ETVR_GAZE_CLOCK_MONOTONIC_NS 2 /* clock_gettime(CLOCK_MONOTONIC), in ns */

/* A sample older than this (publish_time_ns vs. now) means the writer stalled. */
#define ETVR_GAZE_STALE_NS 100000000LL /* 100 ms */

#define ETVR_GAZE_EYE_LEFT 0
#define ETVR_GAZE_EYE_RIGHT 1
#define ETVR_GAZE_EYE_COMBINED 2

#define ETVR_GAZE_FLAG_GAZE_VALID 0x1u     /* direction is usable */
#define ETVR_GAZE_FLAG_OPENNESS_VALID 0x2u /* openness is usable */

typedef struct etvr_gaze_eye {
    /* Unit gaze direction in head (HMD) space, OpenXR convention:
     * +X right, +Y up, -Z forward. */
    float direction[3];
    float openness;   /* 0 closed .. 1 open */
    float confidence; /* 0 .. 1; 1 for every valid sample in version 1 */
    uint32_t flags;   /* ETVR_GAZE_FLAG_* */
    float reserved[2];
} etvr_gaze_eye; /* 32 bytes */

typedef struct etvr_gaze {
    char magic[4];    /* "ETVG" */
    uint16_t version; /* ETVR_GAZE_VERSION */
    uint16_t size;    /* ETVR_GAZE_SIZE */
    uint32_t seq;     /* seqlock: odd while the writer is mid-update */
    uint32_t crc32;   /* CRC-32 (zlib) of bytes ETVR_GAZE_CRC_START..ETVR_GAZE_SIZE */

    /* --- covered by crc32 --- */
    uint32_t clock;          /* ETVR_GAZE_CLOCK_* */
    uint32_t sample_count;   /* +1 per sample; 0 = nothing published yet */
    uint64_t publisher_pid;
    int64_t publish_time_ns; /* when this sample was written */
    int64_t sample_time_ns;  /* camera capture time of the newest frame used */
    etvr_gaze_eye eyes[3];   /* ETVR_GAZE_EYE_* */
    /* Angles the calibrated gaze range maps to, informational. */
    float fov_yaw_max_deg;
    float fov_pitch_up_deg;
    float fov_pitch_down_deg;
    uint8_t reserved[100];
} etvr_gaze; /* 256 bytes */

#if defined(__cplusplus)
static_assert(sizeof(etvr_gaze_eye) == 32, "etvr_gaze_eye layout");
static_assert(sizeof(etvr_gaze) == ETVR_GAZE_SIZE, "etvr_gaze layout");
#elif defined(__STDC_VERSION__) && __STDC_VERSION__ >= 201112L
_Static_assert(sizeof(etvr_gaze_eye) == 32, "etvr_gaze_eye layout");
_Static_assert(sizeof(etvr_gaze) == ETVR_GAZE_SIZE, "etvr_gaze layout");
#endif

static inline uint32_t etvr_gaze_crc32(const uint8_t* data, size_t len) {
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int k = 0; k < 8; k++)
            crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

#if defined(_MSC_VER) && defined(_M_ARM64)
#include <intrin.h>
#define ETVR_GAZE_FENCE() __dmb(_ARM64_BARRIER_ISH)
#elif defined(_MSC_VER)
#include <intrin.h>
#define ETVR_GAZE_FENCE() _ReadWriteBarrier() /* x86/x64 never reorders loads with loads */
#else
#define ETVR_GAZE_FENCE() __atomic_thread_fence(__ATOMIC_SEQ_CST)
#endif

/* Copy a consistent sample out of the mapped block.
 * Returns 1 on success, 0 if the block is mid-update, torn, or not version 1.
 * Retry a few times on 0; the writer updates in well under a microsecond. */
static inline int etvr_gaze_read(const volatile void* shared, etvr_gaze* out) {
    const volatile etvr_gaze* src = (const volatile etvr_gaze*)shared;
    uint32_t seq1 = src->seq;
    ETVR_GAZE_FENCE();
    if (seq1 & 1u)
        return 0;
    memcpy(out, (const void*)src, sizeof(*out));
    ETVR_GAZE_FENCE();
    if (src->seq != seq1)
        return 0;
    if (memcmp(out->magic, ETVR_GAZE_MAGIC, 4) != 0 || out->version != ETVR_GAZE_VERSION ||
        out->size != ETVR_GAZE_SIZE)
        return 0;
    return etvr_gaze_crc32((const uint8_t*)out + ETVR_GAZE_CRC_START, ETVR_GAZE_SIZE - ETVR_GAZE_CRC_START) ==
           out->crc32;
}

/* Combined gaze is usable and fresh. now_ns must be in out->clock's domain. */
static inline int etvr_gaze_usable(const etvr_gaze* g, int64_t now_ns) {
    return g->sample_count != 0 && (g->eyes[ETVR_GAZE_EYE_COMBINED].flags & ETVR_GAZE_FLAG_GAZE_VALID) &&
           now_ns - g->publish_time_ns < ETVR_GAZE_STALE_NS;
}

#ifdef __cplusplus
}
#endif

#endif /* EYETRACKVR_GAZE_H */
