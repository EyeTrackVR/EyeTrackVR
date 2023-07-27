from typing import Iterable

import pydantic
from pydantic import BaseModel


class MissingValidationModelError(Exception):
    pass


class BaseValidationModel(BaseModel):
    pass


class SettingsModule:

    def __init__(self, settings, widget_id, **kwargs):
        self.validation_model: BaseValidationModel = None

        self.settings = settings
        self.widget_id = widget_id
        self.kwargs = kwargs

    def get_layout(self) -> Iterable:
        raise NotImplementedError

    def get_validated_model(self, values):
        validation_model = getattr(self, "validation_model", None)
        if not validation_model:
            raise MissingValidationModelError("Validation model is not set")

        field_mapping = {}
        for field in self.validation_model.schema().get("properties"):
            field_mapping[field] = values[getattr(self, field)]

        return validation_model(**field_mapping)

    def validate(self, values) -> (dict[str, str], dict[str, str]):
        """Returns a tuple of validated data and an empty dict of errors, or vice versa"""
        try:
            changes = {}
            validated_model = self.get_validated_model(values)
            for field, value in validated_model.dict().items():
                if getattr(self.config, field) != value:
                    changes[field] = value
            return changes, None

        except pydantic.ValidationError as e:
            return None, e.errors()
