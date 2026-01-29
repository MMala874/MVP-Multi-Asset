from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from configs.loader import load_config
from configs.models import Config


EXAMPLE_PATH = Path(__file__).resolve().parents[1] / "configs" / "examples" / "example_config.yaml"


def load_example_data():
    return yaml.safe_load(EXAMPLE_PATH.read_text(encoding="utf-8"))


def test_load_example_config():
    config = load_config(EXAMPLE_PATH)
    assert isinstance(config, Config)


def test_allow_bar0_false_only():
    data = load_example_data()
    data["bar_contract"]["allow_bar0"] = True
    with pytest.raises(ValidationError):
        Config.model_validate(data)


def test_bar_contract_must_be_close_open_next():
    data = load_example_data()
    data["bar_contract"]["signal_on"] = "open"
    with pytest.raises(ValidationError):
        Config.model_validate(data)

    data = load_example_data()
    data["bar_contract"]["fill_on"] = "close"
    with pytest.raises(ValidationError):
        Config.model_validate(data)


@pytest.mark.parametrize("missing_block", ["risk", "costs", "strategies"])
def test_missing_block_fails(missing_block):
    data = load_example_data()
    data.pop(missing_block)
    with pytest.raises(ValidationError):
        Config.model_validate(data)
