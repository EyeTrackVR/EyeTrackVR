"""The suite never touches the developer's real EyeTrackVR folder or the
checkout: every place the app writes user files resolves inside the test's own
folder (conftest.isolated_user_data)."""

import os
from pathlib import Path

import config
import data_collection
import ransac
from eye import EyeId
from utils import logging_utils, user_data

CHECKOUT = Path(__file__).resolve().parent.parent


def _inside(path, folder):
    return Path(path).resolve().is_relative_to(Path(folder).resolve())


def test_every_user_file_lands_in_the_tests_own_folder(isolated_user_data):
    paths = [
        user_data.user_data_path("eyetrack_settings.json"),
        config.CONFIG_FILE_NAME,
        config.BACKUP_CONFIG_FILE_NAME,
        ransac.ransac_blink_file_path(EyeId.LEFT),
        data_collection.capture_dir(),
        logging_utils.log_directory(),
    ]
    assert all(_inside(path, isolated_user_data) for path in paths), paths


def test_settings_screens_save_to_the_same_isolated_file(isolated_user_data):
    from settings import base_settings

    assert base_settings.CONFIG_FILE_NAME == config.CONFIG_FILE_NAME
    assert base_settings.BACKUP_CONFIG_FILE_NAME == config.BACKUP_CONFIG_FILE_NAME


def test_relative_paths_resolve_outside_the_checkout():
    assert not _inside(os.getcwd(), CHECKOUT)


def test_each_test_gets_a_fresh_folder(isolated_user_data):
    assert list(isolated_user_data.iterdir()) == []
