from typing import Iterable, Optional, NamedTuple, Any

import pydantic
from pydantic import BaseModel, ConfigDict

from config import EyeTrackSettingsConfig


class MissingValidationModelException(Exception):
    pass


class MissingValidationConfigException(Exception):
    pass


class BaseValidationModel(BaseModel):
    # Every float field rejects NaN and infinity the way it rejects text that is no number
    # (common_field_validators.finite_float). NaN never equals itself, so the page would
    # report it as a change on every tick, and it must not reach the tracking or the config.
    model_config = ConfigDict(allow_inf_nan=False)


class ValidationResult(NamedTuple):
    changes: Optional[dict[str, str]]
    errors: list[Any]  # ErrorDict but we cannot import it, it's not exposed


class BaseSettingsModule:
    def __init__(self, config: EyeTrackSettingsConfig, widget_id, **kwargs):
        self.validation_model: BaseValidationModel = BaseValidationModel  # noqa
        self.config = config
        self.widget_id = widget_id
        self.tk_vars = {}
        # Fields a widget already wrote into the config for instant effect. They no
        # longer differ from it, so validate() reports them from here to get them saved.
        self.live_changes: dict = {}

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
        """Return"""
        if not self.config:
            raise MissingValidationConfigException()
        try:
            validated_model = self.initialize_validation_model(values)
            changes, self.live_changes = self.live_changes, {}
            for field, value in validated_model.model_dump().items():
                if getattr(self.config, field) != value:
                    changes[field] = value

            return ValidationResult(changes, [])
        except pydantic.ValidationError as e:
            if not raise_exception:
                return ValidationResult(None, e.errors())
            raise

    def apply_external_changes(self, data: dict) -> None:
        """Put settings changed outside this page into its widgets."""
        fields = self.get_validation_model().model_fields
        for field, value in data.items():
            var = self.tk_vars.get(getattr(self, field, None)) if field in fields else None
            if var is None:
                continue
            try:
                if var.get() != value:
                    var.set(value)
            except Exception:  # a var of another type, or a destroyed widget
                pass

    def get_layout(self) -> Iterable:
        raise NotImplementedError

    def build(self, parent):
        raise NotImplementedError

    def get_values_map(self) -> dict:
        return {key: var.get() for key, var in self.tk_vars.items()}

    def get_key_for_panel_defaults(self) -> dict:
        return self.validation_model.model_fields.keys()
