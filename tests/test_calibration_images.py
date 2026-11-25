"""IBO / EBPD calibration images (intensity_based_openness,
ellipse_based_pupil_dilation): kept in the user data folder (with the old
working-directory copy still honoured), written off the tracking thread, and
no per-frame percentile over the whole filter window."""

import os
import threading

import numpy as np
import pytest

import ellipse_based_pupil_dilation as ebpd_module
import intensity_based_openness as ibo_module
from eye import EyeId

MODULES = [
    pytest.param(ibo_module, ibo_module.IntensityBasedOpeness, "IBO_LEFT.png", id="ibo"),
    pytest.param(ebpd_module, ebpd_module.EllipseBasedPupilDilation, "EBPD_LEFT.png", id="ebpd"),
]


def _calibration(module, shape, maxval):
    data = np.zeros((shape[0], shape[1] + 1), dtype=np.uint32)
    data[5, 5] = 1234
    data[0, -1] = maxval
    return module.u32_1ch_to_u16_3ch(data)


@pytest.mark.parametrize("module", [ibo_module, ebpd_module], ids=["ibo", "ebpd"])
def test_32_bit_counts_survive_the_16_bit_png_encoding(module):
    data = np.array([[0, 1, 0xFFFF, 0x10000, 0xFFFFFFFF, 123456789]], dtype=np.uint32)
    encoded = module.u32_1ch_to_u16_3ch(data)
    assert encoded.dtype == np.uint16 and encoded.shape == (1, 6, 3)
    np.testing.assert_array_equal(module.u16_3ch_to_u32_1ch(encoded), data)


@pytest.mark.parametrize("module,cls,name", MODULES)
def test_calibration_from_the_working_directory_is_still_loaded(module, cls, name):
    # Builds before the user data folder wrote to the working directory.
    assert module.cv2.imwrite(name, _calibration(module, (20, 30), 777))
    tracker = cls(EyeId.LEFT)

    tracker.load((20, 30))

    assert tracker.maxval == 777
    assert tracker.data[5, 5] == 1234


@pytest.mark.parametrize("module,cls,name", MODULES)
def test_calibration_is_saved_to_the_user_data_folder_off_the_calling_thread(
    isolated_user_data, monkeypatch, module, cls, name
):
    writers = []
    real_imwrite = module.cv2.imwrite

    def recording_imwrite(path, img):
        writers.append(threading.current_thread())
        return real_imwrite(path, img)

    monkeypatch.setattr(module.cv2, "imwrite", recording_imwrite)
    tracker = cls(EyeId.LEFT)
    tracker.load((20, 30))
    tracker.data[5, 5] = 99

    tracker.save()
    tracker.data[5, 5] = 1  # the tracking thread keeps updating its live copy
    tracker._save_thread.join(timeout=5)

    assert writers and writers[0] is not threading.current_thread()
    saved = module.cv2.imread(str(isolated_user_data / name), module.cv2.IMREAD_UNCHANGED)
    assert module.u16_3ch_to_u32_1ch(saved)[5, 5] == 99


@pytest.mark.parametrize("module,cls,name", MODULES)
def test_clearing_calibration_also_removes_the_old_working_directory_copy(isolated_user_data, module, cls, name):
    module.cv2.imwrite(name, _calibration(module, (20, 30), 777))
    module.cv2.imwrite(str(isolated_user_data / name), _calibration(module, (20, 30), 777))
    tracker = cls(EyeId.LEFT)

    tracker.clear_filter()

    assert not os.path.exists(name)
    assert not (isolated_user_data / name).exists()


def _feed(tracker, frames):
    frame = np.full((20, 30), 100, dtype=np.uint8)
    for i in range(frames):
        if isinstance(tracker, ibo_module.IntensityBasedOpeness):
            tracker.intense(10, 10, frame, 1000, 0)
        else:
            tracker.intense(8.0 + i % 3, 8.0, 10, 10, frame, 1000, 0)


@pytest.mark.parametrize("module,cls,name", MODULES)
def test_outlier_percentile_is_not_recomputed_every_frame(count_calls, module, cls, name):
    tracker = cls(EyeId.LEFT)
    tracker.filterlist.extend([1.0] * 500)  # a long, established window
    calls = count_calls(module.np, "percentile")

    _feed(tracker, 30)

    assert len(calls) <= 4
