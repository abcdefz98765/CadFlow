"""Executable examples backed by real CadFlow product and regression paths."""

from .canonical_product_golden import (
    PRODUCT_GOLDEN_PROMPT,
    open_canonical_product_golden,
)
from .golden_desktop_robot_arm import compare_golden_actual_to_expected, run_golden_desktop_robot_arm

__all__ = [
    "PRODUCT_GOLDEN_PROMPT",
    "compare_golden_actual_to_expected",
    "open_canonical_product_golden",
    "run_golden_desktop_robot_arm",
]
