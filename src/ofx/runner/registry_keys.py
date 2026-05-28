"""Standard registry key names for runners."""

from enum import StrEnum


class RunnerRegistryKeys(StrEnum):
    MODEL = "model"
    OUTPUTS = "outputs"
    RESULT = "result"
    EXECUTION = "execution"
    ERRORS = "errors"
    SUMMARY = "workflow:summary"
    SUMMARY_UNIFIED = "workflow:summary:unified"


__all__ = ["RunnerRegistryKeys"]
