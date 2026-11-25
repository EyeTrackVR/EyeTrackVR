"""Release names (utils/version_utils.py) order the way the update check needs: betas,
then release candidates, then the final release; hotfixes (BETA 5.1, RC 1.1) after
their base; a name that is no version never counts as an update."""

import pytest

from utils.version_utils import compare_app_versions, parse_app_version


@pytest.mark.parametrize(
    "older, newer",
    [
        ("EyeTrackApp 0.2.5.6", "EyeTrackApp 0.3.0 BETA 7"),  # a beta of a newer version beats a four-part release
        ("EyeTrackApp 0.3.0 BETA 7", "EyeTrackApp 0.3.0 BETA 8"),
        ("0.3.0 beta 8", "v0.3.0"),  # the final release is newer than its betas
        # Release candidates sit between the betas and the final release.
        ("EyeTrackApp 0.3.0 BETA 11", "EyeTrackApp 0.3.0 RC1"),
        ("EyeTrackApp 0.3.0 BETA 12", "EyeTrackApp 0.3.0 RC1"),
        ("EyeTrackApp 0.3.0 RC1", "EyeTrackApp 0.3.0 RC2"),
        ("EyeTrackApp 0.3.0 RC1", "v0.3.0"),
        # Hotfixes: newer than their base, older than the next stage number.
        ("EyeTrackApp 0.3.0 BETA 5", "EyeTrackApp 0.3.0 BETA 5.1"),
        ("EyeTrackApp 0.3.0 BETA 5.1", "EyeTrackApp 0.3.0 BETA 6"),
        ("EyeTrackApp 0.3.0 RC1", "EyeTrackApp 0.3.0 RC 1.1"),
        ("EyeTrackApp 0.3.0 RC 1.1", "EyeTrackApp 0.3.0 RC2"),
        ("EyeTrackApp 0.3.0 BETA 12.3", "EyeTrackApp 0.3.0 RC1"),
        ("EyeTrackApp 0.3.0 RC 1.1", "EyeTrackApp 0.3.0"),
    ],
)
def test_release_order(older, newer):
    assert compare_app_versions(older, newer) == -1
    assert compare_app_versions(newer, older) == 1


@pytest.mark.parametrize(
    "a, b",
    [
        ("EyeTrackApp 0.3.0", "0.3.0.0"),  # padding
        ("EyeTrackApp 0.3.0 RC 1", "EyeTrackApp 0.3.0 RC 1.0"),  # a zero hotfix is the same release
        ("0.3.0-RC1", "EyeTrackApp 0.3.0 RC1"),  # tag and release name
    ],
)
def test_the_same_release_written_differently(a, b):
    assert compare_app_versions(a, b) == 0


def test_a_tag_parses_like_its_release_name():
    assert parse_app_version("0.3.0-RC1") == parse_app_version("EyeTrackApp 0.3.0 RC1")


def test_unrecognised_release_name_is_not_treated_as_an_update():
    assert parse_app_version("nightly") is None
    assert compare_app_versions("EyeTrackApp 0.3.0", "nightly") is None
