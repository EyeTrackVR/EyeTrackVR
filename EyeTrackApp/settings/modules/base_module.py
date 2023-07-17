from typing import Iterable

from pydantic import BaseModel


class ValidationBaseSettingsDataModel(BaseModel):
    pass


class SettingsModule:

    def __init__(self, settings, widget_id, **kwargs):
        self.initial_model: ValidationBaseSettingsDataModel = None
        self.modified_model: ValidationBaseSettingsDataModel = None

        self.settings = settings
        self.widget_id = widget_id
        self.kwargs = kwargs

    def get_layout(self) -> Iterable:
        raise NotImplementedError

    def validate(self, values) -> (dict[str, str], dict[str, str]):
        """Returns a tuple of validated data and an empty dict of errors, or vice versa"""
        raise NotImplementedError