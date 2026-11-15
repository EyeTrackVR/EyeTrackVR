"""A user's Scan must re-enumerate UVC cameras even inside the invalidation rate limit."""

import camera_enum


def test_forced_invalidate_bypasses_the_rate_limit(monkeypatch):
    calls = []

    def enumerate_now():
        calls.append(1)
        return [{"index": len(calls), "name": "cam", "address": "index:0"}]

    monkeypatch.setattr(camera_enum, "_list_uvc_cameras_uncached", enumerate_now)
    monkeypatch.setattr(camera_enum, "_uvc_list_cache", None)
    monkeypatch.setattr(camera_enum, "_uvc_list_cache_last_invalidated", -999.0)

    camera_enum.list_uvc_cameras()
    camera_enum.invalidate_uvc_camera_cache()  # e.g. after a camera opened
    camera_enum.list_uvc_cameras()
    assert len(calls) == 2

    camera_enum.invalidate_uvc_camera_cache()  # rate-limited: cache kept
    camera_enum.list_uvc_cameras()
    assert len(calls) == 2

    camera_enum.invalidate_uvc_camera_cache(force=True)  # Scan button
    assert camera_enum.list_uvc_cameras()[0]["index"] == 3
