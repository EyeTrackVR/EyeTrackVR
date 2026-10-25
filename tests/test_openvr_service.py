import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class FakeApplicationError(Exception):
    pass


def _load_openvr_service_module():
    fake_openvr = types.ModuleType("openvr")
    fake_openvr.VRApplication_Background = 3
    fake_openvr.init = Mock()
    fake_openvr.shutdown = Mock()
    fake_openvr.IVRApplications = Mock()
    fake_openvr.error_code = types.SimpleNamespace(
        InitError_Init_NoServerForBackgroundApp=type(
            "InitError_Init_NoServerForBackgroundApp", (Exception,), {}
        ),
        InitError_Init_HmdNotFound=type("InitError_Init_HmdNotFound", (Exception,), {}),
        InitError_Init_HmdNotFoundPresenceFailed=type(
            "InitError_Init_HmdNotFoundPresenceFailed", (Exception,), {}
        ),
        InitError_Init_PathRegistryNotFound=type(
            "InitError_Init_PathRegistryNotFound", (Exception,), {}
        ),
    )

    fake_colorama = types.ModuleType("colorama")
    fake_colorama.Fore = types.SimpleNamespace(GREEN="", CYAN="", YELLOW="")

    fake_localization = types.ModuleType("localization")
    fake_localization.tr = lambda key, **kwargs: key.format(**kwargs)

    module_path = Path(__file__).parents[1] / "EyeTrackApp" / "OVR" / "OpenVRService.py"
    spec = importlib.util.spec_from_file_location("openvr_service_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "openvr": fake_openvr,
            "colorama": fake_colorama,
            "localization": fake_localization,
        },
    ):
        spec.loader.exec_module(module)
    return module


class OpenVRServiceRegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_openvr_service_module()

    def _service_with_api(self):
        service = self.module.OpenVRService()
        service.initialize = Mock(return_value=True)
        service.write_manifest = Mock()
        service.app = Mock()
        return service

    def test_none_return_from_binding_is_success(self):
        service = self._service_with_api()
        service.app.addApplicationManifest.return_value = None
        service.app.setApplicationAutoLaunch.return_value = None

        service.set_autostart(True)

        service.app.addApplicationManifest.assert_called_once_with(service.manifestPath)
        service.app.setApplicationAutoLaunch.assert_called_once_with(service.appKey, True)
        self.assertTrue(service.autostart_enabled)

    def test_binding_exception_becomes_actionable_openvr_error(self):
        service = self._service_with_api()
        service.app.addApplicationManifest.side_effect = FakeApplicationError()

        with self.assertRaisesRegex(
            self.module.OpenVRException,
            "Register manifest failed: FakeApplicationError",
        ):
            service.set_autostart(True)

        service.app.setApplicationAutoLaunch.assert_not_called()


if __name__ == "__main__":
    unittest.main()


# --- SteamVR start/stop robustness -------------------------------------------------
import os
import subprocess
import threading
import time

import pytest


class _KeyTaken(Exception):
    pass


@pytest.fixture
def ovr():
    module = _load_openvr_service_module()
    fake = module.openvr
    fake.error_code.ApplicationError_AppKeyAlreadyExists = _KeyTaken
    fake.VRApplicationProperty_BinaryPath_String = "binary"
    fake.VRApplicationProperty_Arguments_String = "arguments"
    fake.VREvent_Quit = 700
    return module


def _connected(module):
    service = module.OpenVRService()
    service.app = Mock()
    service.app.isApplicationInstalled.return_value = False
    service.is_initialized = True
    service.write_manifest = Mock()
    return service


def test_source_manifest_quotes_script_and_sets_working_directory(ovr, monkeypatch, tmp_path):
    script = tmp_path / "with space" / "eyetrackapp.py"
    script.parent.mkdir()
    script.write_text("", encoding="utf-8")
    monkeypatch.setattr(ovr.sys, "argv", [str(script)])
    monkeypatch.setattr(ovr, "_is_frozen", lambda: False)
    app = ovr.OpenVRService()._build_manifest()["applications"][0]
    assert app["arguments"] == '"' + str(script) + '"'
    assert app["working_directory"] == str(script.parent)
    assert ovr._unquote(app["arguments"]) == str(script)


def test_registration_from_another_install_is_replaced(ovr, monkeypatch):
    service = _connected(ovr)
    monkeypatch.setattr(ovr, "_launch_target", lambda: (r"C:\new\EyeTrackApp.exe", ""))
    monkeypatch.setattr(ovr, "_app_dir", lambda: r"C:\new")
    service.app.isApplicationInstalled.return_value = True
    service.app.getApplicationPropertyString.side_effect = lambda key, prop: (
        r"C:\old\EyeTrackApp.exe" if prop == "binary" else "")
    service._register_connected()
    service.app.removeApplicationManifest.assert_called_once_with(os.path.join(r"C:\old", "app.vrmanifest"))
    service.app.addApplicationManifest.assert_called_once()
    service.app.setApplicationAutoLaunch.assert_called_once_with(service.appKey, True)


def test_same_install_is_not_removed(ovr, monkeypatch):
    service = _connected(ovr)
    monkeypatch.setattr(ovr, "_launch_target", lambda: (r"C:\app\EyeTrackApp.exe", ""))
    service.app.isApplicationInstalled.return_value = True
    service.app.getApplicationPropertyString.side_effect = lambda key, prop: (
        r"C:\app\EyeTrackApp.exe" if prop == "binary" else "")
    service._register_connected()
    service.app.removeApplicationManifest.assert_not_called()


def test_taken_app_key_is_reregistered(ovr):
    service = _connected(ovr)
    service.app.addApplicationManifest.side_effect = [_KeyTaken(), None]
    service._register_connected()
    assert service.app.addApplicationManifest.call_count == 2
    service.app.removeApplicationManifest.assert_called_once_with(service.manifestPath)
    assert service._registered


def test_quit_event_is_acknowledged_before_exit(ovr):
    service = _connected(ovr)
    service.autostart_enabled = True
    service._next_liveness = float("inf")
    system = Mock()
    events = iter([True, False])
    def poll(event):
        event.eventType = ovr.openvr.VREvent_Quit
        return next(events)
    system.pollNextEvent.side_effect = poll
    ovr.openvr.VRSystem = Mock(return_value=system)
    ovr.openvr.VREvent_t = lambda: type("Event", (), {})()
    assert service.poll_quit_event() is True
    system.acknowledgeQuit_Exiting.assert_called_once()
    assert not service.is_initialized


def test_crashed_steamvr_drops_connection_for_reconnect(ovr):
    service = _connected(ovr)
    service.autostart_enabled = True
    service._server_gone = True
    ovr.openvr.shutdown.reset_mock()
    assert service.poll_quit_event() is False
    assert not service.is_initialized and not service._registered
    ovr.openvr.shutdown.assert_called_once()


def test_steamvr_started_later_connects_in_background_and_registers(ovr, monkeypatch):
    service = ovr.OpenVRService()
    service.autostart_enabled = True
    app = Mock()
    app.isApplicationInstalled.return_value = False
    ovr.openvr.IVRApplications = Mock(return_value=app)
    ovr.openvr.init = Mock()
    service.write_manifest = Mock()
    started = []
    real_thread = threading.Thread
    def thread(*args, **kwargs):
        t = real_thread(*args, **kwargs)
        started.append(t)
        return t
    monkeypatch.setattr(ovr.threading, "Thread", thread)
    assert service.poll_quit_event() is False  # never blocks the Tk thread
    started[0].join(5)
    assert service.is_initialized and service._registered
    app.addApplicationManifest.assert_called_once()
    app.identifyApplication.assert_called_once_with(os.getpid(), service.appKey)
    # A closed SteamVR is retried no more often than the reconnect interval.
    service._shutdown()
    ovr.openvr.init.side_effect = ovr.openvr.error_code.InitError_Init_NoServerForBackgroundApp()
    service.poll_quit_event()
    assert len(started) == 1


def test_enabling_while_steamvr_closed_is_soft(ovr):
    service = ovr.OpenVRService()
    service.write_manifest = Mock()
    ovr.openvr.init = Mock(side_effect=ovr.openvr.error_code.InitError_Init_NoServerForBackgroundApp())
    service.set_autostart(True)
    assert service.autostart_enabled and service._next_reconnect == 0.0
    service.write_manifest.assert_called_once()


def test_second_instance_is_refused(tmp_path):
    import sys as _sys
    from pathlib import Path as _Path
    app_dir = _Path(__file__).parents[1] / "EyeTrackApp"
    lock = tmp_path / "eyetrackapp.lock"
    code = ("import sys; sys.path.insert(0, sys.argv[1]); from utils import single_instance; "
            "print(single_instance.acquire(sys.argv[2]))")
    holder = subprocess.Popen([_sys.executable, "-u", "-c", code + "; import time; time.sleep(3)", str(app_dir), str(lock)],
                              stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "True"
        second = subprocess.run([_sys.executable, "-c", code, str(app_dir), str(lock)],
                                capture_output=True, text=True, timeout=30)
        assert second.stdout.strip() == "False"
    finally:
        holder.kill()
        holder.wait()
    # The OS releases the lock with the process: the next start is never blocked.
    third = subprocess.run([_sys.executable, "-c", code, str(app_dir), str(lock)],
                           capture_output=True, text=True, timeout=30)
    assert third.stdout.strip() == "True"
