"""Unit tests for incremental build cache helpers."""

from pathlib import Path

from bruno_to_robot.cache import BuildCache, BuildOptions


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestBuildCache:
    """Tests for per-folder fingerprints and build signatures."""

    def test_request_paths_fingerprint_changes_only_for_selected_requests(self, tmp_path: Path):
        """Planner-driven request path fingerprints should react only to selected files."""
        cache = BuildCache()
        _write_file(tmp_path / "Health Check.bru", "meta {\n  name: Health Check\n}\n")
        _write_file(
            tmp_path / "Scenario Batch" / "Client Flow" / "Step 1.bru",
            "meta {\n  name: Step 1\n}\n",
        )

        first = cache.compute_request_paths_fingerprint(
            tmp_path,
            ["Health Check.bru"],
        )

        _write_file(
            tmp_path / "Scenario Batch" / "Client Flow" / "Step 1.bru",
            "meta {\n  name: Step 1 v2\n}\n",
        )
        after_other_change = cache.compute_request_paths_fingerprint(
            tmp_path,
            ["Health Check.bru"],
        )

        _write_file(tmp_path / "Health Check.bru", "meta {\n  name: Health Check v2\n}\n")
        after_selected_change = cache.compute_request_paths_fingerprint(
            tmp_path,
            ["Health Check.bru"],
        )

        assert first == after_other_change
        assert first != after_selected_change

    def test_build_signature_changes_when_split_mode_changes(self, tmp_path: Path):
        """Selected split mode must be part of the planner-driven build signature."""
        cache = BuildCache()

        request_tree = cache.compute_build_signature(
            tmp_path,
            BuildOptions(environment_name="test_client", split_mode="request-tree", input_format="bru"),
        )
        flow_folder = cache.compute_build_signature(
            tmp_path,
            BuildOptions(environment_name="test_client", split_mode="flow-folder", input_format="bru"),
        )

        assert request_tree != flow_folder

    def test_build_signature_changes_when_layout_rules_change(self, tmp_path: Path):
        """Planner layout rules must invalidate the build cache."""
        cache = BuildCache()

        first = cache.compute_build_signature(
            tmp_path,
            BuildOptions(
                environment_name="test_client",
                split_mode="request-tree",
                layout_rules=("Flows=flow-folder",),
                input_format="bru",
            ),
        )
        second = cache.compute_build_signature(
            tmp_path,
            BuildOptions(
                environment_name="test_client",
                split_mode="request-tree",
                layout_rules=("Scenario Batch=flow-folder",),
                input_format="bru",
            ),
        )

        assert first != second

    def test_root_request_fingerprint_changes_only_for_root_level_bru_files(self, tmp_path: Path):
        """Root-request scope should ignore nested folder edits and react to root request edits."""
        cache = BuildCache()
        _write_file(tmp_path / "Health Check.bru", "meta {\n  name: Health Check\n}\n")
        _write_file(tmp_path / "Flows" / "List Customers.bru", "meta {\n  name: List Customers\n}\n")

        first = cache.compute_root_request_fingerprint(tmp_path)

        _write_file(
            tmp_path / "Flows" / "List Customers.bru",
            "meta {\n  name: List Customers v2\n}\n",
        )
        after_nested_change = cache.compute_root_request_fingerprint(tmp_path)

        _write_file(
            tmp_path / "Health Check.bru",
            "meta {\n  name: Health Check v2\n}\n",
        )
        after_root_change = cache.compute_root_request_fingerprint(tmp_path)

        assert first == after_nested_change
        assert first != after_root_change

    def test_folder_fingerprint_changes_when_scoped_folder_changes(self, tmp_path: Path):
        """Editing a `.bru` file inside the folder should invalidate that folder fingerprint."""
        cache = BuildCache()
        _write_file(tmp_path / "customers" / "list.bru", "meta {\n  name: List Customers\n}\n")

        first = cache.compute_folder_fingerprint(tmp_path, Path("customers"))

        _write_file(tmp_path / "customers" / "list.bru", "meta {\n  name: List Customers v2\n}\n")
        second = cache.compute_folder_fingerprint(tmp_path, Path("customers"))

        assert first != second

    def test_folder_fingerprint_ignores_changes_in_other_folders(self, tmp_path: Path):
        """A scoped folder fingerprint should not change when a different folder is edited."""
        cache = BuildCache()
        _write_file(tmp_path / "customers" / "list.bru", "meta {\n  name: List Customers\n}\n")
        _write_file(tmp_path / "wallets" / "detail.bru", "meta {\n  name: Wallet Detail\n}\n")

        first = cache.compute_folder_fingerprint(tmp_path, Path("customers"))

        _write_file(tmp_path / "wallets" / "detail.bru", "meta {\n  name: Wallet Detail v2\n}\n")
        second = cache.compute_folder_fingerprint(tmp_path, Path("customers"))

        assert first == second

    def test_folder_fingerprint_ignores_non_bru_files(self, tmp_path: Path):
        """Non-Bruno files should not invalidate a folder fingerprint."""
        cache = BuildCache()
        _write_file(tmp_path / "customers" / "list.bru", "meta {\n  name: List Customers\n}\n")

        first = cache.compute_folder_fingerprint(tmp_path, Path("customers"))

        _write_file(tmp_path / "customers" / "notes.txt", "scratch notes")
        second = cache.compute_folder_fingerprint(tmp_path, Path("customers"))

        assert first == second

    def test_build_signature_changes_when_environment_changes(self, tmp_path: Path):
        """Selected Bruno environment must be part of the build cache key."""
        cache = BuildCache()

        test_client = cache.compute_build_signature(
            tmp_path,
            BuildOptions(environment_name="test_client", split_by_folder=True),
        )
        devel = cache.compute_build_signature(
            tmp_path,
            BuildOptions(environment_name="devel", split_by_folder=True),
        )

        assert test_client != devel

    def test_build_signature_changes_when_selected_bru_env_file_changes(self, tmp_path: Path):
        """Editing the selected Bruno env file must invalidate the build cache."""
        cache = BuildCache()
        _write_file(tmp_path / "bruno.json", '{"name":"Demo"}')
        _write_file(
            tmp_path / "environments" / "test_client.bru",
            "vars {\n  baseUrl: https://one.example.com\n}\n",
        )

        first = cache.compute_build_signature(
            tmp_path,
            BuildOptions(environment_name="test_client", split_by_folder=True, input_format="bru"),
        )

        _write_file(
            tmp_path / "environments" / "test_client.bru",
            "vars {\n  baseUrl: https://two.example.com\n}\n",
        )
        second = cache.compute_build_signature(
            tmp_path,
            BuildOptions(environment_name="test_client", split_by_folder=True, input_format="bru"),
        )

        assert first != second

    def test_build_signature_changes_when_bruno_manifest_changes(self, tmp_path: Path):
        """Editing `bruno.json` must invalidate the build cache for Bruno directories."""
        cache = BuildCache()
        _write_file(tmp_path / "bruno.json", '{"name":"Demo"}')
        _write_file(
            tmp_path / "environments" / "test_client.bru",
            "vars {\n  baseUrl: https://one.example.com\n}\n",
        )

        first = cache.compute_build_signature(
            tmp_path,
            BuildOptions(environment_name="test_client", split_by_folder=True, input_format="bru"),
        )

        _write_file(tmp_path / "bruno.json", '{"name":"Demo v2"}')
        second = cache.compute_build_signature(
            tmp_path,
            BuildOptions(environment_name="test_client", split_by_folder=True, input_format="bru"),
        )

        assert first != second

    def test_build_signature_changes_when_collection_bru_changes(self, tmp_path: Path):
        """Editing `collection.bru` must invalidate the build cache for native Bruno directories."""
        cache = BuildCache()
        _write_file(tmp_path / "collection.bru", "vars:pre-request {\n  baseUrl: https://one.example.com\n}\n")

        first = cache.compute_build_signature(
            tmp_path,
            BuildOptions(environment_name=None, split_by_folder=True, input_format="bru"),
        )

        _write_file(tmp_path / "collection.bru", "vars:pre-request {\n  baseUrl: https://two.example.com\n}\n")
        second = cache.compute_build_signature(
            tmp_path,
            BuildOptions(environment_name=None, split_by_folder=True, input_format="bru"),
        )

        assert first != second

    def test_build_signature_changes_when_base_url_override_changes(self, tmp_path: Path):
        """Base URL override must invalidate the build cache."""
        cache = BuildCache()

        first = cache.compute_build_signature(
            tmp_path,
            BuildOptions(
                environment_name="test_client",
                split_by_folder=True,
                base_url_override="https://one.example.com",
            ),
        )
        second = cache.compute_build_signature(
            tmp_path,
            BuildOptions(
                environment_name="test_client",
                split_by_folder=True,
                base_url_override="https://two.example.com",
            ),
        )

        assert first != second

    def test_build_signature_changes_when_resource_path_changes(self, tmp_path: Path):
        """Resource path must invalidate the build cache for split builds."""
        cache = BuildCache()

        first = cache.compute_build_signature(
            tmp_path,
            BuildOptions(
                environment_name="test_client",
                split_by_folder=True,
                split_mode="request-tree",
                input_format="bru",
                resource_path="generated/shared/variables.robot",
            ),
        )
        second = cache.compute_build_signature(
            tmp_path,
            BuildOptions(
                environment_name="test_client",
                split_by_folder=True,
                split_mode="request-tree",
                input_format="bru",
                resource_path="generated/resources/vars.robot",
            ),
        )

        assert first != second

    def test_build_signature_changes_when_init_layering_changes(self, tmp_path: Path):
        """Init layering toggle must invalidate split build cache."""
        cache = BuildCache()

        first = cache.compute_build_signature(
            tmp_path,
            BuildOptions(
                environment_name="test_client",
                split_by_folder=True,
                split_mode="request-tree",
                input_format="bru",
                init_layering=False,
            ),
        )
        second = cache.compute_build_signature(
            tmp_path,
            BuildOptions(
                environment_name="test_client",
                split_by_folder=True,
                split_mode="request-tree",
                input_format="bru",
                init_layering=True,
            ),
        )

        assert first != second

    def test_build_signature_changes_when_cache_version_changes(self, tmp_path: Path, monkeypatch):
        """Converter/cache version must be part of the build signature."""
        cache = BuildCache()

        first = cache.compute_build_signature(
            tmp_path,
            BuildOptions(environment_name="test_client", split_by_folder=True, input_format="bru"),
        )

        monkeypatch.setattr(BuildCache, "BUILD_SIGNATURE_VERSION", "test-next")
        second = cache.compute_build_signature(
            tmp_path,
            BuildOptions(environment_name="test_client", split_by_folder=True, input_format="bru"),
        )

        assert first != second
