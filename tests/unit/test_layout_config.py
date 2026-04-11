"""Unit tests for layout config parsing."""

from pathlib import Path

import pytest

from bruno_to_robot.cli import load_layout_config
from bruno_to_robot.output_planner import SplitMode


class TestLayoutConfig:
    """Tests for loading layout planning config files."""

    def test_load_layout_config_reads_default_mode_and_rules(self, tmp_path: Path):
        """Valid config file should return default mode and ordered rules."""
        config_path = tmp_path / "layout.yaml"
        config_path.write_text(
            """default_mode: request-tree
rules:
  - path_prefix: Flows
    mode: flow-folder
  - path_prefix: External
    mode: request-tree
""",
            encoding="utf-8",
        )

        default_mode, rules = load_layout_config(config_path)

        assert default_mode == SplitMode.REQUEST_TREE
        assert [(rule.path_prefix, rule.mode) for rule in rules] == [
            ("Flows", SplitMode.FLOW_FOLDER),
            ("External", SplitMode.REQUEST_TREE),
        ]

    def test_load_layout_config_returns_empty_rules_for_missing_sections(self, tmp_path: Path):
        """Config without rules should still load a valid default mode."""
        config_path = tmp_path / "layout.yaml"
        config_path.write_text("default_mode: flow-folder\n", encoding="utf-8")

        default_mode, rules = load_layout_config(config_path)

        assert default_mode == SplitMode.FLOW_FOLDER
        assert rules == []

    def test_load_layout_config_rejects_invalid_rule_shape(self, tmp_path: Path):
        """Each rule must define both path_prefix and mode."""
        config_path = tmp_path / "layout.yaml"
        config_path.write_text(
            """rules:
  - path_prefix: Flows
""",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="layout config"):
            load_layout_config(config_path)
