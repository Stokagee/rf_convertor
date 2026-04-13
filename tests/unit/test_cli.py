"""Unit tests for the CLI entry point."""

import shutil
from pathlib import Path

from click.testing import CliRunner

from bruno_to_robot.cli import detect_format, main


class TestCli:
    """Tests for CLI options and parser wiring."""

    def test_cli_help_mentions_bru_and_environment_support(self):
        """CLI help should advertise direct Bruno input and env selection."""
        runner = CliRunner()

        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "--format [bru|json|yaml]" in result.output
        assert "--env TEXT" in result.output
        assert "Bruno request, or" in result.output

    def test_cli_help_mentions_split_mode_option(self):
        """CLI help should expose future layout modes for large collections."""
        runner = CliRunner()

        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "--split-mode [single|top-folder|request-tree|flow-folder]" in result.output
        assert "--layout-rule TEXT" in result.output
        assert "--layout-config PATH" in result.output
        assert "--init-layering / --no-init-layering" in result.output

    def test_detect_format_supports_bru_file(self):
        """`.bru` files should auto-detect as Bruno input."""
        assert detect_format(Path("request.bru")) == "bru"

    def test_detect_format_supports_bru_directory(self, bru_collection_dir: Path):
        """Bruno directories should auto-detect without an explicit `--format`."""
        assert detect_format(bru_collection_dir) == "bru"

    def test_cli_selects_named_environment(
        self,
        fixtures_dir: Path,
        tmp_path: Path,
    ):
        """`--env` should select the requested Bruno environment."""
        runner = CliRunner()
        input_path = fixtures_dir / "bruno_export_multi_env.yaml"
        output_path = tmp_path / "selected_env.robot"

        result = runner.invoke(
            main,
            [
                "-i",
                str(input_path),
                "-o",
                str(output_path),
                "--env",
                "test_client",
            ],
        )

        assert result.exit_code == 0
        assert output_path.exists()

        content = output_path.read_text(encoding="utf-8")
        assert "https://client.example.com" in content
        assert "https://dev.example.com" not in content

    def test_cli_fails_for_unknown_environment(
        self,
        fixtures_dir: Path,
        tmp_path: Path,
    ):
        """Unknown `--env` values should fail fast."""
        runner = CliRunner()
        input_path = fixtures_dir / "bruno_export_multi_env.yaml"
        output_path = tmp_path / "missing_env.robot"

        result = runner.invoke(
            main,
            [
                "-i",
                str(input_path),
                "-o",
                str(output_path),
                "--env",
                "missing-env",
            ],
        )

        assert result.exit_code == 1

    def test_cli_autodetects_bru_directory(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Directory input should parse as Bruno and generate Robot output."""
        runner = CliRunner()
        output_path = tmp_path / "bru_collection.robot"

        result = runner.invoke(
            main,
            [
                "-i",
                str(bru_collection_dir),
                "-o",
                str(output_path),
                "--env",
                "test_client",
            ],
        )

        assert result.exit_code == 0
        assert output_path.exists()

        content = output_path.read_text(encoding="utf-8")
        assert "Health Check" in content
        assert "https://client.example.com" in content

    def test_cli_autodetects_single_bru_file(
        self,
        bru_single_request_path: Path,
        tmp_path: Path,
    ):
        """A direct `.bru` request file should work without forcing `--format`."""
        runner = CliRunner()
        output_path = tmp_path / "single_bru.robot"

        result = runner.invoke(
            main,
            [
                "-i",
                str(bru_single_request_path),
                "-o",
                str(output_path),
            ],
        )

        assert result.exit_code == 0
        assert output_path.exists()

        content = output_path.read_text(encoding="utf-8")
        assert "Get Health" in content

    def test_cli_split_mode_single_generates_one_output_file(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """`--split-mode single` should keep directory input in one output suite file."""
        runner = CliRunner()
        output_path = tmp_path / "single_mode.robot"

        result = runner.invoke(
            main,
            [
                "-i",
                str(bru_collection_dir),
                "-o",
                str(output_path),
                "--env",
                "test_client",
                "--split-mode",
                "single",
            ],
        )

        assert result.exit_code == 0
        assert output_path.exists()
        assert not (tmp_path / "flows.robot").exists()

        content = output_path.read_text(encoding="utf-8")
        assert "Health Check" in content
        assert "List Customers" in content

    def test_cli_split_mode_top_folder_matches_legacy_split_output(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """`--split-mode top-folder` should produce the same files as legacy `--split`."""
        runner = CliRunner()
        output_dir = tmp_path / "generated"

        result = runner.invoke(
            main,
            [
                "-i",
                str(bru_collection_dir),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "top-folder",
            ],
        )

        assert result.exit_code == 0
        assert (output_dir / "flows.robot").exists()
        assert (output_dir / "paymont_bruno_collection.robot").exists()

    def test_cli_split_mode_overrides_legacy_split_flag(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Explicit `--split-mode` should win over the legacy split flag for compatibility."""
        runner = CliRunner()
        output_path = tmp_path / "single_override.robot"

        result = runner.invoke(
            main,
            [
                "-i",
                str(bru_collection_dir),
                "-o",
                str(output_path),
                "--env",
                "test_client",
                "--split",
                "--split-mode",
                "single",
            ],
        )

        assert result.exit_code == 0
        assert output_path.exists()
        assert not (tmp_path / "flows.robot").exists()

    def test_cli_split_mode_request_tree_generates_one_robot_file_per_request(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """`request-tree` should generate one `.robot` file per Bruno request path."""
        runner = CliRunner()
        output_dir = tmp_path / "generated"

        result = runner.invoke(
            main,
            [
                "-i",
                str(bru_collection_dir),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "request-tree",
            ],
        )

        assert result.exit_code == 0
        assert (output_dir / "health_check.robot").exists()
        assert (output_dir / "flows" / "client_api_flow" / "get_oauth2_token.robot").exists()
        assert (output_dir / "flows" / "client_api_flow" / "list_customers.robot").exists()
        assert not (output_dir / "flows.robot").exists()

    def test_cli_split_mode_request_tree_generates_single_test_case_per_file(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Each request-tree output file should contain only the mapped request test case."""
        runner = CliRunner()
        output_dir = tmp_path / "generated"

        result = runner.invoke(
            main,
            [
                "-i",
                str(bru_collection_dir),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "request-tree",
            ],
        )

        assert result.exit_code == 0

        token_suite = output_dir / "flows" / "client_api_flow" / "get_oauth2_token.robot"
        token_content = token_suite.read_text(encoding="utf-8")

        assert "Get Oauth2 Token" in token_content
        assert "List Customers" not in token_content

        health_suite = output_dir / "health_check.robot"
        health_content = health_suite.read_text(encoding="utf-8")

        assert "Health Check" in health_content
        assert "Get Oauth2 Token" not in health_content

    def test_cli_request_tree_handles_slug_collisions_without_overwriting_outputs(
        self,
        tmp_path: Path,
    ):
        """Request-tree generation should keep punctuated/case-colliding slugs separate."""
        runner = CliRunner()
        input_root = tmp_path / "bru_input"
        output_dir = tmp_path / "generated"
        users_dir = input_root / "Users"
        users_dir.mkdir(parents=True, exist_ok=True)
        (users_dir / "Get User.bru").write_text(
            """meta {
  name: Get User
  type: http
  seq: 1
}

get {
  url: https://api.example.com/users/1
}
""",
            encoding="utf-8",
        )
        (users_dir / "Get-User.bru").write_text(
            """meta {
  name: Get-User
  type: http
  seq: 2
}

get {
  url: https://api.example.com/users/2
}
""",
            encoding="utf-8",
        )
        (users_dir / "Get.User.bru").write_text(
            """meta {
  name: Get.User
  type: http
  seq: 3
}

get {
  url: https://api.example.com/users/3
}
""",
            encoding="utf-8",
        )
        (users_dir / "get_user.bru").write_text(
            """meta {
  name: get_user
  type: http
  seq: 4
}

get {
  url: https://api.example.com/users/4
}
""",
            encoding="utf-8",
        )

        result = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--split-mode",
                "request-tree",
            ],
        )

        assert result.exit_code == 0
        assert (output_dir / "users" / "get_user.robot").exists()
        hashed_outputs = sorted((output_dir / "users").glob("get_user_*.robot"))
        assert len(hashed_outputs) == 3

    def test_cli_split_mode_flow_folder_generates_leaf_flow_suite_and_root_request_file(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """`flow-folder` should keep root requests separate and group leaf-folder flows."""
        runner = CliRunner()
        output_dir = tmp_path / "generated"

        result = runner.invoke(
            main,
            [
                "-i",
                str(bru_collection_dir),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "flow-folder",
            ],
        )

        assert result.exit_code == 0
        assert (output_dir / "health_check.robot").exists()
        assert (output_dir / "flows" / "client_api_flow.robot").exists()
        assert not (output_dir / "flows.robot").exists()
        assert not (output_dir / "flows" / "client_api_flow" / "get_oauth2_token.robot").exists()

    def test_cli_split_mode_flow_folder_preserves_request_order_inside_flow_suite(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Flow-folder output should preserve planned request order instead of sorting by test name."""
        runner = CliRunner()
        output_dir = tmp_path / "generated"

        result = runner.invoke(
            main,
            [
                "-i",
                str(bru_collection_dir),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "flow-folder",
            ],
        )

        assert result.exit_code == 0

        flow_suite = output_dir / "flows" / "client_api_flow.robot"
        content = flow_suite.read_text(encoding="utf-8")

        token_index = content.index("Get Oauth2 Token")
        customers_index = content.index("List Customers")
        assert token_index < customers_index

    def test_cli_layout_rule_can_mix_request_tree_with_flow_folder_branch(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Route rules should allow mixed layouts inside one Bruno collection run."""
        runner = CliRunner()
        output_dir = tmp_path / "generated"

        result = runner.invoke(
            main,
            [
                "-i",
                str(bru_collection_dir),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "request-tree",
                "--layout-rule",
                "Flows=flow-folder",
            ],
        )

        assert result.exit_code == 0
        assert (output_dir / "health_check.robot").exists()
        assert (output_dir / "flows" / "client_api_flow.robot").exists()
        assert not (output_dir / "flows" / "client_api_flow" / "get_oauth2_token.robot").exists()

    def test_cli_layout_rule_supports_wildcard_path_prefix(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Wildcard path prefixes should route matching nested folders to the configured mode."""
        runner = CliRunner()
        output_dir = tmp_path / "generated"

        result = runner.invoke(
            main,
            [
                "-i",
                str(bru_collection_dir),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "request-tree",
                "--layout-rule",
                "Flows/*=flow-folder",
            ],
        )

        assert result.exit_code == 0
        assert (output_dir / "health_check.robot").exists()
        assert (output_dir / "flows" / "client_api_flow.robot").exists()
        assert not (output_dir / "flows" / "client_api_flow" / "get_oauth2_token.robot").exists()

    def test_cli_layout_rule_matches_case_insensitively(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Lowercase wildcard route should match uppercase Bruno folder names."""
        runner = CliRunner()
        output_dir = tmp_path / "generated"

        result = runner.invoke(
            main,
            [
                "-i",
                str(bru_collection_dir),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "request-tree",
                "--layout-rule",
                "flows/*=flow-folder",
            ],
        )

        assert result.exit_code == 0
        assert (output_dir / "flows" / "client_api_flow.robot").exists()
        assert not (output_dir / "flows" / "client_api_flow" / "get_oauth2_token.robot").exists()

    def test_cli_rejects_invalid_layout_rule_syntax(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Invalid layout rule syntax should fail fast with a clear error."""
        runner = CliRunner()
        output_dir = tmp_path / "generated"

        result = runner.invoke(
            main,
            [
                "-i",
                str(bru_collection_dir),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "request-tree",
                "--layout-rule",
                "Flows",
            ],
        )

        assert result.exit_code == 1
        assert "PATH_PREFIX=SPLIT_MODE" in result.output

    def test_cli_layout_config_can_mix_request_tree_with_flow_folder_branch(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Layout config file should route selected branches without repeating CLI rules."""
        runner = CliRunner()
        output_dir = tmp_path / "generated"
        config_path = tmp_path / "layout.yaml"
        config_path.write_text(
            """default_mode: request-tree
rules:
  - path_prefix: Flows
    mode: flow-folder
""",
            encoding="utf-8",
        )

        result = runner.invoke(
            main,
            [
                "-i",
                str(bru_collection_dir),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--layout-config",
                str(config_path),
            ],
        )

        assert result.exit_code == 0
        assert (output_dir / "health_check.robot").exists()
        assert (output_dir / "flows" / "client_api_flow.robot").exists()
        assert not (output_dir / "flows" / "client_api_flow" / "get_oauth2_token.robot").exists()

    def test_cli_split_mode_overrides_layout_config_default_mode(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Explicit CLI split mode should win over config default mode."""
        runner = CliRunner()
        output_dir = tmp_path / "generated"
        config_path = tmp_path / "layout.yaml"
        config_path.write_text(
            """default_mode: flow-folder
""",
            encoding="utf-8",
        )

        result = runner.invoke(
            main,
            [
                "-i",
                str(bru_collection_dir),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--layout-config",
                str(config_path),
                "--split-mode",
                "request-tree",
            ],
        )

        assert result.exit_code == 0
        assert (output_dir / "flows" / "client_api_flow" / "get_oauth2_token.robot").exists()
        assert not (output_dir / "flows" / "client_api_flow.robot").exists()

    def test_cli_layout_rule_overrides_layout_config_rule(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Explicit CLI rules should be evaluated before config rules."""
        runner = CliRunner()
        output_dir = tmp_path / "generated"
        config_path = tmp_path / "layout.yaml"
        config_path.write_text(
            """default_mode: request-tree
rules:
  - path_prefix: Flows
    mode: request-tree
""",
            encoding="utf-8",
        )

        result = runner.invoke(
            main,
            [
                "-i",
                str(bru_collection_dir),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--layout-config",
                str(config_path),
                "--layout-rule",
                "Flows=flow-folder",
            ],
        )

        assert result.exit_code == 0
        assert (output_dir / "flows" / "client_api_flow.robot").exists()
        assert not (output_dir / "flows" / "client_api_flow" / "get_oauth2_token.robot").exists()

    def test_cli_rejects_invalid_layout_config(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Invalid layout config should fail with a clear validation error."""
        runner = CliRunner()
        output_dir = tmp_path / "generated"
        config_path = tmp_path / "layout.yaml"
        config_path.write_text(
            """rules:
  - path_prefix: Flows
    mode: not-a-mode
""",
            encoding="utf-8",
        )

        result = runner.invoke(
            main,
            [
                "-i",
                str(bru_collection_dir),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--layout-config",
                str(config_path),
            ],
        )

        assert result.exit_code == 1
        assert "layout config" in result.output.lower()

    def test_cli_split_bru_directory_uses_cache_on_unchanged_second_run(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Second split build of the same Bruno directory should reuse cached suites."""
        runner = CliRunner()
        input_root = tmp_path / "bru_input"
        output_dir = tmp_path / "generated"
        shutil.copytree(bru_collection_dir, input_root)

        first = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split",
            ],
        )
        second = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split",
            ],
        )

        assert first.exit_code == 0
        assert second.exit_code == 0
        assert f"Cached: {output_dir / 'flows.robot'}" in second.output
        assert f"Cached: {output_dir / 'paymont_bruno_collection.robot'}" in second.output

    def test_cli_request_tree_uses_cache_on_unchanged_second_run(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Planner-driven request-tree cache should reuse unchanged request suites."""
        runner = CliRunner()
        input_root = tmp_path / "bru_input"
        output_dir = tmp_path / "generated"
        shutil.copytree(bru_collection_dir, input_root)

        first = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "request-tree",
            ],
        )
        second = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "request-tree",
            ],
        )

        assert first.exit_code == 0
        assert second.exit_code == 0
        assert f"Cached: {output_dir / 'health_check.robot'}" in second.output
        assert (
            f"Cached: {output_dir / 'flows' / 'client_api_flow' / 'get_oauth2_token.robot'}"
            in second.output
        )
        assert (
            f"Cached: {output_dir / 'flows' / 'client_api_flow' / 'list_customers.robot'}"
            in second.output
        )

    def test_cli_request_tree_regenerates_only_changed_request_file(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Editing one request in request-tree mode should invalidate only its suite file."""
        runner = CliRunner()
        input_root = tmp_path / "bru_input"
        output_dir = tmp_path / "generated"
        shutil.copytree(bru_collection_dir, input_root)

        first = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "request-tree",
            ],
        )
        assert first.exit_code == 0

        target_file = input_root / "Flows" / "Client API Flow" / "List Customers.bru"
        target_file.write_text(
            """meta {
  name: List Customers
  type: http
  seq: 2
}

get {
  url: {{baseUrl}}/customers
}

params:query {
  size: 50
}
""",
            encoding="utf-8",
        )

        second = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "request-tree",
            ],
        )

        assert second.exit_code == 0
        assert (
            f"Generated: {output_dir / 'flows' / 'client_api_flow' / 'list_customers.robot'}"
            in second.output
        )
        assert (
            f"Cached: {output_dir / 'flows' / 'client_api_flow' / 'get_oauth2_token.robot'}"
            in second.output
        )
        assert f"Cached: {output_dir / 'health_check.robot'}" in second.output

    def test_cli_mixed_layout_rules_invalidate_only_changed_flow_suite(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Mixed planner rules should cache root requests separately from grouped flow suites."""
        runner = CliRunner()
        input_root = tmp_path / "bru_input"
        output_dir = tmp_path / "generated"
        shutil.copytree(bru_collection_dir, input_root)

        first = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "request-tree",
                "--layout-rule",
                "Flows=flow-folder",
            ],
        )
        assert first.exit_code == 0

        target_file = input_root / "Flows" / "Client API Flow" / "List Customers.bru"
        target_file.write_text(
            """meta {
  name: List Customers
  type: http
  seq: 2
}

get {
  url: {{baseUrl}}/customers
}

params:query {
  size: 50
}
""",
            encoding="utf-8",
        )

        second = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "request-tree",
                "--layout-rule",
                "Flows=flow-folder",
            ],
        )

        assert second.exit_code == 0
        assert f"Generated: {output_dir / 'flows' / 'client_api_flow.robot'}" in second.output
        assert f"Cached: {output_dir / 'health_check.robot'}" in second.output

    def test_cli_split_bru_directory_regenerates_only_changed_folder_suite(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Editing one Bruno folder should invalidate only that split suite."""
        runner = CliRunner()
        input_root = tmp_path / "bru_input"
        output_dir = tmp_path / "generated"
        shutil.copytree(bru_collection_dir, input_root)

        first = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split",
            ],
        )
        assert first.exit_code == 0

        target_file = input_root / "Flows" / "Client API Flow" / "List Customers.bru"
        target_file.write_text(
            """meta {
  name: List Customers
  type: http
  seq: 2
}

get {
  url: {{baseUrl}}/customers
}

params:query {
  size: 50
}
""",
            encoding="utf-8",
        )

        second = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split",
            ],
        )

        assert second.exit_code == 0
        assert f"Generated: {output_dir / 'flows.robot'}" in second.output
        assert f"Cached: {output_dir / 'paymont_bruno_collection.robot'}" in second.output

    def test_cli_split_bru_directory_invalidates_cache_when_env_changes(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Changing the selected Bruno env should invalidate the cached suites."""
        runner = CliRunner()
        input_root = tmp_path / "bru_input"
        output_dir = tmp_path / "generated"
        shutil.copytree(bru_collection_dir, input_root)

        first = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split",
            ],
        )
        second = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "devel",
                "--split",
            ],
        )

        assert first.exit_code == 0
        assert second.exit_code == 0
        assert f"Generated: {output_dir / 'flows.robot'}" in second.output
        assert f"Generated: {output_dir / 'paymont_bruno_collection.robot'}" in second.output

    def test_cli_split_bru_directory_invalidates_cache_when_selected_env_file_changes(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Editing the selected Bruno env file should regenerate cached suites."""
        runner = CliRunner()
        input_root = tmp_path / "bru_input"
        output_dir = tmp_path / "generated"
        shutil.copytree(bru_collection_dir, input_root)

        first = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split",
            ],
        )
        assert first.exit_code == 0

        env_file = input_root / "environments" / "test_client.bru"
        env_file.write_text(
            """vars {
  baseUrl: https://changed.example.com
  access_token: client-token
}
""",
            encoding="utf-8",
        )

        second = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split",
            ],
        )

        assert second.exit_code == 0
        assert f"Generated: {output_dir / 'flows.robot'}" in second.output
        assert f"Generated: {output_dir / 'paymont_bruno_collection.robot'}" in second.output

    def test_cli_split_bru_directory_removes_stale_folder_suite_when_folder_is_deleted(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Deleting a top-level Bruno folder should remove its stale split suite output."""
        runner = CliRunner()
        input_root = tmp_path / "bru_input"
        output_dir = tmp_path / "generated"
        shutil.copytree(bru_collection_dir, input_root)

        first = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split",
            ],
        )
        assert first.exit_code == 0
        assert (output_dir / "flows.robot").exists()

        shutil.rmtree(input_root / "Flows")

        second = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split",
            ],
        )

        assert second.exit_code == 0
        assert f"Removed stale: {output_dir / 'flows.robot'}" in second.output
        assert not (output_dir / "flows.robot").exists()

    def test_cli_split_bru_directory_removes_stale_root_suite_when_root_requests_disappear(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Deleting root-level Bruno requests should remove the stale root suite file."""
        runner = CliRunner()
        input_root = tmp_path / "bru_input"
        output_dir = tmp_path / "generated"
        shutil.copytree(bru_collection_dir, input_root)

        first = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split",
            ],
        )
        assert first.exit_code == 0
        assert (output_dir / "paymont_bruno_collection.robot").exists()

        (input_root / "Health Check.bru").unlink()

        second = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split",
            ],
        )

        assert second.exit_code == 0
        assert (
            f"Removed stale: {output_dir / 'paymont_bruno_collection.robot'}"
            in second.output
        )
        assert not (output_dir / "paymont_bruno_collection.robot").exists()

    def test_cli_split_yaml_generates_helper_library_for_scripted_suite(
        self,
        fixtures_dir: Path,
        tmp_path: Path,
    ):
        """Split output should generate and import helper libraries for suites with scripts."""
        runner = CliRunner()
        input_path = fixtures_dir / "split_helper_collection.yaml"
        output_dir = tmp_path / "generated"

        result = runner.invoke(
            main,
            [
                "-i",
                str(input_path),
                "-o",
                str(output_dir),
                "--split",
            ],
        )

        assert result.exit_code == 0

        suite_path = output_dir / "users.robot"
        helper_path = output_dir / "users_helpers.py"

        assert suite_path.exists()
        assert helper_path.exists()

        suite_content = suite_path.read_text(encoding="utf-8")
        helper_content = helper_path.read_text(encoding="utf-8")

        assert "Library           ${CURDIR}${/}users_helpers.py" in suite_content
        assert "def generate_create_random_user_body():" in helper_content

    def test_cli_request_tree_with_resource_imports_shared_variables_using_relative_paths(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Shared resource should be imported relatively from root and nested request-tree suites."""
        runner = CliRunner()
        output_dir = tmp_path / "generated"
        resource_path = output_dir / "shared" / "variables.robot"

        result = runner.invoke(
            main,
            [
                "-i",
                str(bru_collection_dir),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "request-tree",
                "--resource",
                str(resource_path),
            ],
        )

        assert result.exit_code == 0
        assert resource_path.exists()

        root_suite = output_dir / "health_check.robot"
        nested_suite = output_dir / "flows" / "client_api_flow" / "get_oauth2_token.robot"
        resource_content = resource_path.read_text(encoding="utf-8")

        assert "Resource          shared/variables.robot" in root_suite.read_text(encoding="utf-8")
        assert (
            "Resource          ../../shared/variables.robot"
            in nested_suite.read_text(encoding="utf-8")
        )
        assert "${BASE_URL}" in resource_content

    def test_cli_request_tree_init_layering_generates_shared_keywords_and_root_init_file(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Init layering should move suite keywords to shared resource and create `__init__.robot`."""
        runner = CliRunner()
        output_dir = tmp_path / "generated"

        result = runner.invoke(
            main,
            [
                "-i",
                str(bru_collection_dir),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "request-tree",
                "--init-layering",
            ],
        )

        assert result.exit_code == 0

        shared_keywords = output_dir / "_shared" / "common_keywords.robot"
        root_init = output_dir / "__init__.robot"
        root_suite = output_dir / "health_check.robot"
        nested_suite = output_dir / "flows" / "client_api_flow" / "get_oauth2_token.robot"

        assert shared_keywords.exists()
        assert root_init.exists()

        root_content = root_suite.read_text(encoding="utf-8")
        nested_content = nested_suite.read_text(encoding="utf-8")
        init_content = root_init.read_text(encoding="utf-8")

        assert "*** Keywords ***" not in root_content
        assert "Resource          _shared/common_keywords.robot" in root_content
        assert "Resource          ../../_shared/common_keywords.robot" in nested_content
        assert "Resource          _shared/common_keywords.robot" in init_content

    def test_cli_request_tree_rebuilds_cached_suites_when_init_layering_option_changes(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Turning on init layering should invalidate split cache and regenerate suite files."""
        runner = CliRunner()
        input_root = tmp_path / "bru_input"
        output_dir = tmp_path / "generated"
        shutil.copytree(bru_collection_dir, input_root)

        first = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "request-tree",
            ],
        )
        second = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "request-tree",
                "--init-layering",
            ],
        )

        assert first.exit_code == 0
        assert second.exit_code == 0
        assert f"Generated: {output_dir / 'health_check.robot'}" in second.output
        assert (output_dir / "_shared" / "common_keywords.robot").exists()

    def test_cli_request_tree_rebuilds_cached_suites_when_resource_option_changes(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Turning on `--resource` should invalidate split cache and regenerate suite files."""
        runner = CliRunner()
        input_root = tmp_path / "bru_input"
        output_dir = tmp_path / "generated"
        resource_path = output_dir / "shared" / "variables.robot"
        shutil.copytree(bru_collection_dir, input_root)

        first = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "request-tree",
            ],
        )
        second = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split-mode",
                "request-tree",
                "--resource",
                str(resource_path),
            ],
        )

        assert first.exit_code == 0
        assert second.exit_code == 0
        assert f"Generated: {output_dir / 'health_check.robot'}" in second.output
        assert resource_path.exists()

        content = (output_dir / "health_check.robot").read_text(encoding="utf-8")
        assert "Resource          shared/variables.robot" in content

    def test_cli_single_output_with_resource_imports_shared_variables(
        self,
        fixtures_dir: Path,
        tmp_path: Path,
    ):
        """Single-suite output should import requested resource and keep variables there."""
        runner = CliRunner()
        input_path = fixtures_dir / "bruno_export_multi_env.yaml"
        output_path = tmp_path / "robot" / "api.robot"
        resource_path = tmp_path / "robot" / "resources" / "vars.robot"

        result = runner.invoke(
            main,
            [
                "-i",
                str(input_path),
                "-o",
                str(output_path),
                "--env",
                "test_client",
                "--resource",
                str(resource_path),
            ],
        )

        assert result.exit_code == 0
        assert output_path.exists()
        assert resource_path.exists()

        suite_content = output_path.read_text(encoding="utf-8")
        resource_content = resource_path.read_text(encoding="utf-8")
        assert "Resource          resources/vars.robot" in suite_content
        assert "${BASE_URL}" in resource_content

    def test_cli_split_native_bru_directory_invalidates_cache_when_collection_file_changes(
        self,
        bru_native_collection_dir: Path,
        tmp_path: Path,
    ):
        """Changing `collection.bru` should invalidate cached split suites."""
        runner = CliRunner()
        input_root = tmp_path / "bru_input"
        output_dir = tmp_path / "generated"
        shutil.copytree(bru_native_collection_dir, input_root)

        first = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split",
            ],
        )
        assert first.exit_code == 0

        collection_file = input_root / "collection.bru"
        collection_file.write_text(
            """vars:pre-request {
  baseUrl: https://changed.example.com
  apiVersion: v2
}
""",
            encoding="utf-8",
        )

        second = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--split",
            ],
        )

        assert second.exit_code == 0
        assert f"Generated: {output_dir / 'user_management.robot'}" in second.output

    def test_cli_autodiscovers_layout_config_from_bru_root(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Bruno directory root config should be used when `--layout-config` is omitted."""
        runner = CliRunner()
        input_root = tmp_path / "bru_input"
        output_dir = tmp_path / "generated"
        shutil.copytree(bru_collection_dir, input_root)
        (input_root / "bruno-to-robot.layout.yaml").write_text(
            """default_mode: request-tree
rules:
  - path_prefix: Flows
    mode: flow-folder
""",
            encoding="utf-8",
        )

        result = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
            ],
        )

        assert result.exit_code == 0
        assert (output_dir / "health_check.robot").exists()
        assert (output_dir / "flows" / "client_api_flow.robot").exists()
        assert not (output_dir / "flows" / "client_api_flow" / "get_oauth2_token.robot").exists()

    def test_cli_explicit_layout_config_overrides_autodiscovered_root_config(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """`--layout-config` should take precedence over implicit root config discovery."""
        runner = CliRunner()
        input_root = tmp_path / "bru_input"
        output_dir = tmp_path / "generated"
        explicit_config = tmp_path / "explicit-layout.yaml"
        shutil.copytree(bru_collection_dir, input_root)
        (input_root / "bruno-to-robot.layout.yaml").write_text(
            "default_mode: flow-folder\n",
            encoding="utf-8",
        )
        explicit_config.write_text(
            "default_mode: request-tree\n",
            encoding="utf-8",
        )

        result = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
                "--layout-config",
                str(explicit_config),
            ],
        )

        assert result.exit_code == 0
        assert (output_dir / "flows" / "client_api_flow" / "get_oauth2_token.robot").exists()
        assert not (output_dir / "flows" / "client_api_flow.robot").exists()

    def test_cli_fails_for_invalid_autodiscovered_layout_config(
        self,
        bru_collection_dir: Path,
        tmp_path: Path,
    ):
        """Invalid root layout config should fail fast with a validation error."""
        runner = CliRunner()
        input_root = tmp_path / "bru_input"
        output_dir = tmp_path / "generated"
        shutil.copytree(bru_collection_dir, input_root)
        (input_root / "bruno-to-robot.layout.yaml").write_text(
            """default_mode: unsupported-mode
""",
            encoding="utf-8",
        )

        result = runner.invoke(
            main,
            [
                "-i",
                str(input_root),
                "-o",
                str(output_dir),
                "--env",
                "test_client",
            ],
        )

        assert result.exit_code == 1
        assert "layout config" in result.output.lower()
