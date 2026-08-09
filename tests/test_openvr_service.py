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
