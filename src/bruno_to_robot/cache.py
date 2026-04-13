"""Helpers for incremental build cache keys and planner-driven fingerprints."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class BuildOptions:
    """Inputs that affect generated output even if source files stay unchanged."""

    environment_name: str | None = None
    split_by_folder: bool = False
    split_mode: str | None = None
    layout_rules: tuple[str, ...] = ()
    base_url_override: str | None = None
    session_name: str = "api"
    input_format: str | None = None
    resource_path: str | None = None
    init_layering: bool = False


class BuildCache:
    """Compute deterministic cache keys for Bruno collection builds."""

    CACHE_FILE_NAME = ".bruno_to_robot_cache.json"
    TRACKED_SUFFIXES = {".bru"}
    BUILD_SIGNATURE_VERSION = "1"

    def compute_build_signature(self, input_path: str | Path, options: BuildOptions) -> str:
        """Return a stable signature for the current build options."""
        path = Path(input_path)
        payload = {
            "input_path": str(path.resolve()),
            "build_signature_version": self.BUILD_SIGNATURE_VERSION,
            **asdict(options),
        }
        if options.input_format == "bru" and path.is_dir():
            payload["shared_inputs_fingerprint"] = self.compute_shared_input_fingerprint(
                path,
                environment_name=options.environment_name,
            )
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def compute_folder_fingerprint(
        self,
        input_root: str | Path,
        relative_folder: str | Path | None = None,
    ) -> str:
        """Return a stable fingerprint for `.bru` files under a folder scope."""
        root = Path(input_root)
        scope = root / Path(relative_folder) if relative_folder else root

        hasher = hashlib.sha256()

        if not scope.exists():
            hasher.update(b"missing")
            return hasher.hexdigest()

        for file_path in self._iter_tracked_files(scope):
            relative_path = file_path.relative_to(root).as_posix()
            hasher.update(relative_path.encode("utf-8"))
            hasher.update(file_path.read_bytes())

        return hasher.hexdigest()

    def compute_request_paths_fingerprint(
        self,
        input_root: str | Path,
        request_paths: list[str],
    ) -> str:
        """Return a stable fingerprint for an explicit ordered list of Bruno request files."""
        root = Path(input_root)
        hasher = hashlib.sha256()

        if not root.exists():
            hasher.update(b"missing")
            return hasher.hexdigest()

        for request_path in request_paths:
            file_path = root / Path(request_path)
            hasher.update(request_path.encode("utf-8"))
            if file_path.exists():
                hasher.update(file_path.read_bytes())
            else:
                hasher.update(b"missing")

        return hasher.hexdigest()

    def compute_root_request_fingerprint(self, input_root: str | Path) -> str:
        """Return a fingerprint for root-level `.bru` files only."""
        root = Path(input_root)
        hasher = hashlib.sha256()

        if not root.exists():
            hasher.update(b"missing")
            return hasher.hexdigest()

        for file_path in self._iter_tracked_files(root, recursive=False):
            relative_path = file_path.relative_to(root).as_posix()
            hasher.update(relative_path.encode("utf-8"))
            hasher.update(file_path.read_bytes())

        return hasher.hexdigest()

    def compute_shared_input_fingerprint(
        self,
        input_root: str | Path,
        environment_name: str | None = None,
    ) -> str:
        """Return a fingerprint for Bruno inputs shared across split suites."""
        root = Path(input_root)
        hasher = hashlib.sha256()

        manifest_path = root / "bruno.json"
        self._update_hasher_with_optional_file(hasher, root, manifest_path)

        collection_path = root / "collection.bru"
        self._update_hasher_with_optional_file(hasher, root, collection_path)

        env_path = self._get_selected_environment_file(root, environment_name)
        if env_path is None:
            hasher.update(b"env:none")
        else:
            self._update_hasher_with_optional_file(hasher, root, env_path)

        return hasher.hexdigest()

    def load_manifest(self, output_dir: str | Path) -> dict[str, Any]:
        """Load a previously stored build cache manifest from the output directory."""
        manifest_path = Path(output_dir) / self.CACHE_FILE_NAME
        if not manifest_path.exists():
            return {}

        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def write_manifest(
        self,
        output_dir: str | Path,
        build_signature: str,
        suites: dict[str, dict[str, str]],
    ) -> None:
        """Persist suite fingerprints for the current build."""
        manifest_path = Path(output_dir) / self.CACHE_FILE_NAME
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = {
            "build_signature": build_signature,
            "suites": suites,
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _get_selected_environment_file(
        self,
        root: Path,
        environment_name: str | None,
    ) -> Path | None:
        """Return the Bruno environment file that would be selected for this build."""
        environments_dir = root / "environments"
        env_files = sorted(environments_dir.glob("*.bru"), key=lambda item: item.stem.lower())

        if not env_files:
            return None

        if environment_name is None:
            return env_files[0]

        for env_file in env_files:
            if env_file.stem == environment_name:
                return env_file

        return None

    def _update_hasher_with_optional_file(
        self,
        hasher: Any,
        root: Path,
        file_path: Path,
    ) -> None:
        """Hash a file path and contents, or record that it is missing."""
        relative_path = file_path.relative_to(root).as_posix()
        hasher.update(relative_path.encode("utf-8"))

        if file_path.exists():
            hasher.update(file_path.read_bytes())
        else:
            hasher.update(b"missing")

    def _iter_tracked_files(self, scope: Path, recursive: bool = True) -> list[Path]:
        """Return tracked source files in deterministic order."""
        candidates = (
            scope.rglob("*")
            if recursive
            else (path for path in scope.iterdir() if path.is_file())
        )
        return sorted(
            (
                path
                for path in candidates
                if path.is_file() and path.suffix.lower() in self.TRACKED_SUFFIXES
            ),
            key=lambda path: path.as_posix().lower(),
        )
