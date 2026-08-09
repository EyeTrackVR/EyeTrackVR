from EyeTrackApp.utils.version_utils import compare_app_versions, parse_app_version


def test_beta_build_is_newer_than_older_four_part_release():
    assert (
        compare_app_versions(
            "EyeTrackApp 0.3.0 BETA 7", "EyeTrackApp 0.2.5.6"
        )
        == 1
    )


def test_newer_beta_build_is_an_update():
    assert (
        compare_app_versions(
            "EyeTrackApp 0.3.0 BETA 7", "EyeTrackApp 0.3.0 BETA 8"
        )
        == -1
    )


def test_final_release_is_newer_than_beta_of_same_version():
    assert compare_app_versions("0.3.0 beta 8", "v0.3.0") == -1


def test_differently_padded_numeric_versions_compare_equal():
    assert compare_app_versions("EyeTrackApp 0.3.0", "0.3.0.0") == 0


def test_unrecognised_release_name_is_not_treated_as_an_update():
    assert parse_app_version("nightly") is None
    assert compare_app_versions("EyeTrackApp 0.3.0", "nightly") is None
