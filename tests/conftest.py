import tempfile
from pathlib import Path

import pytest

from ai_native_cad.generator import get_part_spec
from ai_native_cad.runner import load_builder


@pytest.fixture(scope="module")
def mounting_plate_model():
    spec = get_part_spec("mounting_plate")
    return load_builder("mounting_plate")(spec), spec


@pytest.fixture(scope="module")
def circular_button_model():
    spec = get_part_spec("circular_button")
    return load_builder("circular_button")(spec), spec


@pytest.fixture(scope="module")
def enclosure_base_model():
    spec = get_part_spec("enclosure_base")
    return load_builder("enclosure_base")(spec), spec


@pytest.fixture(scope="module")
def enclosure_lid_model():
    spec = get_part_spec("enclosure_lid")
    return load_builder("enclosure_lid")(spec), spec


@pytest.fixture(scope="module")
def spacer_model():
    spec = get_part_spec("spacer")
    return load_builder("spacer")(spec), spec


@pytest.fixture(scope="module")
def wall_bracket_model():
    spec = get_part_spec("wall_bracket")
    return load_builder("wall_bracket")(spec), spec


@pytest.fixture
def tmp_output_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)
