from typing import Iterable, Optional, NamedTuple, Any

import pydantic
from pydantic import BaseModel

from config import EyeTrackSettingsConfig


class MissingValidationModelException(Exception):
    pass


class MissingValidationConfigException(Exception):
    pass


class BaseValidationModel(BaseModel):
    pass


class ValidationResult(NamedTuple):
    changes: Optional[dict[str, str]]
    errors: list[Any]  # ErrorDict but we cannot import it, it's not exposed


class BaseSettingsModule:
    def __init__(self, config: EyeTrackSettingsConfig, widget_id, **kwargs):
        self.validation_model: BaseValidationModel = BaseValidationModel  # noqa
        self.config = config
        self.widget_id = widget_id

    def get_validation_model(self):
        """Return validation model, can be overridden for custom behaviour"""
        return self.validation_model

    def initialize_validation_model(self, values):
        validation_model = self.get_validation_model()
        if not validation_model:
            raise MissingValidationModelException()

        field_mapping = {}
        for field in self.validation_model.model_fields.keys():
            field_mapping[field] = values[getattr(self, field)]

        return validation_model(**field_mapping)

    def validate(self, values, raise_exception=False) -> Optional[ValidationResult]:
        """Return """
        if not self.config:
            raise MissingValidationConfigException()
        try:
            changes = {}
            validated_model = self.initialize_validation_model(values)
            for field, value in validated_model.model_dump().items():
                if getattr(self.config, field) != value:
                    changes[field] = value

            return ValidationResult(changes, [])
        except pydantic.ValidationError as e:
            if not raise_exception:
                return ValidationResult(None, e.errors())
            raise

    def get_layout(self) -> Iterable:
        raise NotImplementedError

    def get_key_for_panel_defaults(self) -> dict:
        return self.validation_model.schema().get("properties").keys()