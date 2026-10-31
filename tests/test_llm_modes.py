"""Answer modes: every mode the frontend can send must reach its own prompt instructions."""
import os
import re
import sys
from pathlib import Path
from typing import List

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from llm_client import LLMClient

CHAT_INPUT = Path(__file__).resolve().parents[1] / "frontend" / "src" / "components" / "ChatInput.js"


@pytest.fixture
def client() -> LLMClient:
    # _mode_instructions reads no instance state; skipping __init__ avoids needing GEMINI_API_KEY.
    return LLMClient.__new__(LLMClient)


def _frontend_modes() -> List[str]:
    return re.findall(r'<option value="([^"]+)"', CHAT_INPUT.read_text(encoding="utf-8"))


def test_frontend_offers_three_modes() -> None:
    assert _frontend_modes() == ["quick", "detailed", "step-by-step"]


@pytest.mark.parametrize("mode", ["step-by-step", "step_by_step", "Step-By-Step"])
def test_step_by_step_spellings_get_numbered_steps(client: LLMClient, mode: str) -> None:
    assert "numbered steps" in client._mode_instructions(mode)


def test_every_frontend_mode_gets_distinct_instructions(client: LLMClient) -> None:
    instructions = [client._mode_instructions(m) for m in _frontend_modes()]
    assert len(set(instructions)) == len(instructions)


def test_unknown_mode_falls_back_to_detailed(client: LLMClient) -> None:
    assert client._mode_instructions("nonsense") == client._mode_instructions("detailed")
