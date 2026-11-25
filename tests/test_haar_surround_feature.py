"""HSF (haar_surround_feature): each eye thread has scratch buffers of its own,
so two eyes tracked at once each find their own pupil."""

import threading

import cv2
import numpy as np

import haar_surround_feature


def _blob_image(cx, cy, shape=(100, 120), r=8):
    img = np.full(shape, 200, dtype=np.uint8)
    cv2.circle(img, (cx, cy), r, 10, -1)
    return img


def test_hsf_instances_do_not_share_scratch_buffers():
    a = haar_surround_feature.HSF_cls()
    b = haar_surround_feature.HSF_cls()
    key = ((100, 120), 40, 5, 5, 20, 60)

    bufs_a = a._get_buffers(*key)
    bufs_b = b._get_buffers(*key)

    # Same geometry must not mean the same mutable arrays across eyes (the
    # read-only index arrays may stay shared)...
    for arr_a, arr_b in zip(bufs_a, bufs_b):
        if arr_a.flags.writeable:
            assert not np.shares_memory(arr_a, arr_b)
        else:
            assert not arr_b.flags.writeable
    # ...but one instance reuses its own buffers frame to frame.
    assert a._get_buffers(*key)[0] is bufs_a[0]


def test_hsf_two_threads_each_find_their_own_pupil(monkeypatch):
    # External_Run_HSF writes these module globals; restore them afterwards.
    monkeypatch.setattr(haar_surround_feature, "skip_autoradius", False)
    monkeypatch.setattr(haar_surround_feature, "default_radius", 20)

    eyes = {
        "left": ((25, 30), _blob_image(25, 30)),
        "right": ((90, 70), _blob_image(90, 70)),
    }
    results = {name: [] for name in eyes}
    barrier = threading.Barrier(len(eyes))

    def worker(name):
        runner = haar_surround_feature.External_Run_HSF(True, 8)
        _, img = eyes[name]
        barrier.wait()
        for _ in range(250):
            # run() draws markers on its input, so hand it a fresh copy.
            x, y, _, _ = runner.run(img.copy())
            results[name].append((x, y))

    threads = [threading.Thread(target=worker, args=(n,)) for n in eyes]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    for name, ((cx, cy), _) in eyes.items():
        assert len(results[name]) == 250
        for x, y in results[name]:
            assert abs(x - cx) <= 10 and abs(y - cy) <= 10, (name, x, y)
