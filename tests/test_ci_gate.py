"""Deliberately failing test: proves branch protection blocks a red PR. Never merge."""


def test_ci_gate_blocks_merge() -> None:
    assert False, "Day 06 gate test: this PR must be blocked by the required backend check"
