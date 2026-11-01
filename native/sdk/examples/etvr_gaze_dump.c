/*
 * Print EyeTrackVR's gaze shared memory, as a reference reader.
 *
 *   Windows: cl /nologo /W4 etvr_gaze_dump.c /I..
 *   Linux:   cc -O2 -Wall -I.. etvr_gaze_dump.c -o etvr_gaze_dump
 *
 * Usage: etvr_gaze_dump [count] [name]
 *   count  samples to print, ~10 ms apart (default 1)
 *   name   mapping name / shm path, for testing (default: the v1 name)
 */

#include <stdio.h>
#include <stdlib.h>

#include "eyetrackvr_gaze.h"

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

static int64_t now_ns(void) {
    LARGE_INTEGER qpc, freq;
    QueryPerformanceCounter(&qpc);
    QueryPerformanceFrequency(&freq);
    return (int64_t)((double)qpc.QuadPart * 1e9 / (double)freq.QuadPart);
}

static const void* map_gaze(const char* name) {
    wchar_t wide[256];
    if (name)
        MultiByteToWideChar(CP_UTF8, 0, name, -1, wide, 256);
    HANDLE mapping = OpenFileMappingW(FILE_MAP_READ, FALSE, name ? wide : ETVR_GAZE_WIN32_NAME);
    if (!mapping)
        return NULL;
    return MapViewOfFile(mapping, FILE_MAP_READ, 0, 0, ETVR_GAZE_SIZE);
}

static void sleep_ms(int ms) {
    Sleep(ms);
}
#else
#include <fcntl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

static int64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (int64_t)ts.tv_sec * 1000000000LL + ts.tv_nsec;
}

static const void* map_gaze(const char* name) {
    /* A path (test name) is opened directly; the v1 name goes through shm_open. */
    int fd = name ? open(name, O_RDONLY) : shm_open(ETVR_GAZE_POSIX_NAME, O_RDONLY, 0);
    if (fd < 0)
        return NULL;
    void* view = mmap(NULL, ETVR_GAZE_SIZE, PROT_READ, MAP_SHARED, fd, 0);
    close(fd);
    return view == MAP_FAILED ? NULL : view;
}

static void sleep_ms(int ms) {
    usleep(ms * 1000);
}
#endif

static void print_eye(const char* label, const etvr_gaze_eye* e) {
    printf("%s=%.6f,%.6f,%.6f open=%.3f conf=%.3f flags=%u ", label, e->direction[0], e->direction[1],
           e->direction[2], e->openness, e->confidence, e->flags);
}

int main(int argc, char** argv) {
    int count = argc > 1 ? atoi(argv[1]) : 1;
    const void* shared = map_gaze(argc > 2 ? argv[2] : NULL);
    if (!shared) {
        fprintf(stderr, "EyeTrackVR gaze not published (enable \"Foveated rendering gaze\")\n");
        return 2;
    }
    for (int i = 0; i < count; i++) {
        etvr_gaze g;
        int ok = 0;
        for (int retry = 0; retry < 8 && !ok; retry++)
            ok = etvr_gaze_read(shared, &g);
        if (!ok) {
            printf("unreadable\n");
        } else {
            int64_t now = now_ns();
            printf("count=%u clock=%u pid=%llu age_ms=%.3f latency_ms=%.3f usable=%d ", g.sample_count, g.clock,
                   (unsigned long long)g.publisher_pid, (now - g.publish_time_ns) / 1e6,
                   (now - g.sample_time_ns) / 1e6, etvr_gaze_usable(&g, now));
            print_eye("L", &g.eyes[ETVR_GAZE_EYE_LEFT]);
            print_eye("R", &g.eyes[ETVR_GAZE_EYE_RIGHT]);
            print_eye("C", &g.eyes[ETVR_GAZE_EYE_COMBINED]);
            printf("fov=%.1f,%.1f,%.1f\n", g.fov_yaw_max_deg, g.fov_pitch_up_deg, g.fov_pitch_down_deg);
        }
        fflush(stdout);
        if (i + 1 < count)
            sleep_ms(10);
    }
    return 0;
}
