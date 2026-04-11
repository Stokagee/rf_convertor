"""Parser for direct Bruno `.bru` files and collection directories."""

from __future__ import annotations

import json
from pathlib import Path

from bruno_to_robot.models.bruno import (
    BrunoCollection,
    BrunoFolder,
    BrunoRequest,
    BrunoVariable,
)

from .base import BaseParser
from .yaml_parser import ParseError, YamlParser


class BruParser(BaseParser):
    """Parser for a constrained subset of Bruno request files."""

    HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
    SUPPORTED_REQUEST_BLOCKS = {"meta", "headers", "query", "params:query", "docs"}
    SUPPORTED_COLLECTION_BLOCKS = {"vars:pre-request"}
    SUPPORTED_FOLDER_BLOCKS = {"meta"}
    SUPPORTED_ENVIRONMENT_BLOCKS = {"vars"}

    def __init__(self, environment_name: str | None = None) -> None:
        self.environment_name = environment_name
        self._yaml_parser = YamlParser(environment_name=environment_name)

    def parse(self, content: str) -> BrunoCollection:
        """Parse a single `.bru` request payload into a one-request collection."""
        request = self._parse_request_content(content)
        return BrunoCollection(name=request.name, requests=[request])

    def parse_path(self, path: str | Path) -> BrunoCollection:
        """Parse either a single `.bru` file or a Bruno collection directory."""
        path = Path(path)

        if path.is_dir():
            return self._parse_directory(path)

        if path.suffix.lower() != ".bru":
            raise ParseError(f"Unsupported Bruno file: {path}")

        request = self._parse_request_file(path)
        return BrunoCollection(name=request.name, requests=[request])

    def _parse_directory(self, root: Path) -> BrunoCollection:
        """Parse a Bruno collection directory into the internal collection model."""
        manifest = self._read_manifest(root)
        collection_variables = self._load_collection_variables(root)
        environment_variables = self._load_environment_variables(root)
        variables = self._merge_variables(collection_variables, environment_variables)
        folders = []
        requests = []

        for entry in sorted(root.iterdir(), key=lambda item: (item.is_file(), item.name.lower())):
            if entry.name in {"environments", "bruno.json", "collection.bru"}:
                continue

            if entry.is_dir():
                folders.append(self._parse_folder(entry, root))
            elif entry.suffix.lower() == ".bru":
                requests.append(self._parse_request_file(entry, root))

        if not requests and not self._folders_have_requests(folders):
            raise ParseError(f"No Bruno requests found in {root}")

        return BrunoCollection(
            name=manifest.get("name", root.name),
            version=str(manifest.get("version", "1.0")),
            variables=variables,
            base_url=self._extract_base_url_from_variables(variables),
            folders=folders,
            requests=requests,
        )

    def _parse_folder(self, folder_path: Path, root: Path) -> BrunoFolder:
        """Parse a filesystem folder into a BrunoFolder."""
        folders = []
        requests = []
        folder_name = folder_path.name
        folder_metadata_path = folder_path / "folder.bru"

        if folder_metadata_path.exists():
            folder_name = self._read_folder_metadata(folder_metadata_path).get("name", folder_name)

        for entry in sorted(folder_path.iterdir(), key=lambda item: (item.is_file(), item.name.lower())):
            if entry.name == "folder.bru":
                continue
            if entry.is_dir():
                folders.append(self._parse_folder(entry, root))
            elif entry.suffix.lower() == ".bru":
                requests.append(self._parse_request_file(entry, root))

        return BrunoFolder(
            name=folder_name,
            path=folder_path.relative_to(root).as_posix(),
            requests=requests,
            folders=folders,
        )

    def _parse_request_file(self, path: Path, root: Path | None = None) -> BrunoRequest:
        """Parse a `.bru` file from disk."""
        content = path.read_text(encoding="utf-8")
        try:
            request = self._parse_request_content(content)
        except (ParseError, ValueError) as exc:
            raise ParseError(f"Failed to parse {path}: {exc}") from exc
        if root is not None:
            request.path = path.relative_to(root).as_posix()
        return request

    def _parse_request_content(self, content: str) -> BrunoRequest:
        """Parse the supported Bruno request subset."""
        blocks = self._parse_blocks(content)
        self._validate_request_blocks(blocks)
        meta = self._parse_mapping_block(blocks.get("meta", ""))

        method_name, http_block = self._extract_http_block(blocks)
        http_mapping = self._parse_mapping_block(http_block)
        body = self._parse_body_block(blocks)
        auth = self._parse_auth_block(blocks)
        headers = self._parse_mapping_block(blocks.get("headers", ""))
        params = self._parse_mapping_block(
            blocks.get("params:query", blocks.get("query", ""))
        )
        docs = blocks.get("docs")
        url = http_mapping.get("url", "").strip()
        if not url:
            raise ParseError("Bruno request is missing `url`")

        request_data = {
            "info": {
                "name": meta.get("name", "Unnamed Request"),
                "type": meta.get("type", "http"),
                "seq": int(meta.get("seq", "1")),
            },
            "http": {
                "method": method_name.upper(),
                "url": url,
                "headers": headers,
                "params": params,
                "auth": auth or "inherit",
                "body": body,
            },
            "docs": docs,
        }

        return self._yaml_parser._parse_request_item(request_data)

    def _read_manifest(self, root: Path) -> dict:
        """Read `bruno.json` if present."""
        manifest_path = root / "bruno.json"
        if not manifest_path.exists():
            return {}

        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ParseError(f"Invalid bruno.json: {exc}") from exc

    def _load_environment_variables(self, root: Path):
        """Load variables from the selected Bruno environment file, if present."""
        environments_dir = root / "environments"
        if not environments_dir.exists():
            if self.environment_name:
                raise ParseError(f"Environment '{self.environment_name}' not found")
            return []

        env_files = sorted(environments_dir.glob("*.bru"), key=lambda item: item.stem.lower())

        if not env_files:
            if self.environment_name:
                raise ParseError(f"Environment '{self.environment_name}' not found")
            return []

        selected_path = None
        if self.environment_name is None:
            selected_path = env_files[0]
        else:
            for env_path in env_files:
                if env_path.stem == self.environment_name:
                    selected_path = env_path
                    break

        if selected_path is None:
            raise ParseError(f"Environment '{self.environment_name}' not found")

        try:
            blocks = self._parse_blocks(selected_path.read_text(encoding="utf-8"))
        except ParseError as exc:
            raise ParseError(f"Failed to parse {selected_path}: {exc}") from exc
        self._validate_environment_blocks(blocks, selected_path)
        return self._parse_native_variables(blocks.get("vars", ""), selected_path)

    def _load_collection_variables(self, root: Path) -> list[BrunoVariable]:
        """Load supported variables from native `collection.bru`, if present."""
        collection_path = root / "collection.bru"
        if not collection_path.exists():
            return []

        try:
            blocks = self._parse_blocks(collection_path.read_text(encoding="utf-8"))
        except ParseError as exc:
            raise ParseError(f"Failed to parse {collection_path}: {exc}") from exc

        self._validate_collection_blocks(blocks, collection_path)
        return self._parse_native_variables(blocks.get("vars:pre-request", ""), collection_path)

    def _read_folder_metadata(self, path: Path) -> dict[str, str]:
        """Read supported folder metadata from `folder.bru`."""
        try:
            blocks = self._parse_blocks(path.read_text(encoding="utf-8"))
        except ParseError as exc:
            raise ParseError(f"Failed to parse {path}: {exc}") from exc

        self._validate_folder_blocks(blocks, path)
        return self._parse_mapping_block(blocks.get("meta", ""))

    def _extract_base_url_from_variables(self, variables) -> str | None:
        """Derive collection base URL from parsed variables."""
        for variable in variables:
            if variable.name in ("base_url", "baseUrl", "BASE_URL"):
                return str(variable.value) if variable.value else None
        return None

    def _extract_http_block(self, blocks: dict[str, str]) -> tuple[str, str]:
        """Find the request method block."""
        for method in self.HTTP_METHODS:
            if method in blocks:
                return method, blocks[method]
        raise ParseError("Bruno request is missing an HTTP method block")

    def _parse_body_block(self, blocks: dict[str, str]) -> dict | None:
        """Parse the first supported Bruno body block."""
        for block_name, content in blocks.items():
            if not block_name.startswith("body"):
                continue

            if ":" in block_name:
                _, body_type = block_name.split(":", 1)
            else:
                body_type = "text"

            body_type = body_type.strip()
            if body_type in {"form", "form-urlencoded", "multipart-form", "multipart"}:
                data = self._parse_mapping_block(content)
            else:
                data = content.strip()

            return {
                "type": body_type,
                "data": data,
            }

        return None

    def _parse_auth_block(self, blocks: dict[str, str]) -> dict | None:
        """Parse the supported Bruno auth subset."""
        for block_name, content in blocks.items():
            if not block_name.startswith("auth:"):
                continue

            _, auth_type = block_name.split(":", 1)
            auth_type = auth_type.strip()
            auth_data = self._parse_mapping_block(content)
            auth_data["type"] = auth_type
            return auth_data

        return None

    def _parse_mapping_block(self, content: str) -> dict[str, str]:
        """Parse simple `key: value` lines inside a Bruno block."""
        mapping: dict[str, str] = {}

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue

            key, value = line.split(":", 1)
            mapping[key.strip()] = value.strip()

        return mapping

    def _parse_native_variables(self, content: str, path: Path) -> list[BrunoVariable]:
        """Parse native Bruno variables with MVP-safe handling for prefixes."""
        variables: list[BrunoVariable] = []

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue

            raw_name, raw_value = line.split(":", 1)
            name = raw_name.strip()
            value = raw_value.strip()

            if name.startswith("~"):
                continue

            if name.startswith("@"):
                raise ParseError(f"Unsupported local Bruno variable in {path}: {name}")

            variables.append(BrunoVariable(name=name, value=value))

        return variables

    def _parse_blocks(self, content: str) -> dict[str, str]:
        """Parse top-level Bruno blocks with brace matching."""
        blocks: dict[str, str] = {}
        index = 0
        length = len(content)

        while index < length:
            while index < length and content[index].isspace():
                index += 1

            if index >= length:
                break

            header_start = index
            while index < length and content[index] != "{":
                index += 1

            if index >= length:
                break

            header = content[header_start:index].strip()
            index += 1
            body_start = index
            index = self._find_block_end(content, index)

            body = content[body_start:index - 1].strip()
            if header:
                blocks[header] = body

        return blocks

    def _find_block_end(self, content: str, start_index: int) -> int:
        """Return the index just after the matching closing brace for a block body."""
        index = start_index
        length = len(content)
        depth = 1
        string_quote: str | None = None
        escaped = False

        while index < length and depth > 0:
            char = content[index]

            if string_quote is not None:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == string_quote:
                    string_quote = None
            else:
                if char in {'"', "'"}:
                    string_quote = char
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1

            index += 1

        if depth != 0:
            raise ParseError("Invalid Bruno file: unbalanced braces")

        return index

    def _folders_have_requests(self, folders: list[BrunoFolder]) -> bool:
        """Return whether any folder subtree contains at least one request."""
        for folder in folders:
            if folder.requests or self._folders_have_requests(folder.folders):
                return True
        return False

    def _validate_request_blocks(self, blocks: dict[str, str]) -> None:
        """Reject unsupported request-level Bruno blocks instead of silently ignoring them."""
        unsupported = []
        for block_name in blocks:
            if block_name in self.SUPPORTED_REQUEST_BLOCKS:
                continue
            if block_name in self.HTTP_METHODS:
                continue
            if block_name.startswith("body"):
                continue
            if block_name.startswith("auth:"):
                continue
            unsupported.append(block_name)

        if unsupported:
            formatted = ", ".join(sorted(unsupported))
            raise ParseError(f"Unsupported Bruno sections: {formatted}")

    def _validate_collection_blocks(self, blocks: dict[str, str], path: Path) -> None:
        """Reject unsupported native `collection.bru` sections instead of ignoring them."""
        unsupported = sorted(
            block_name for block_name in blocks if block_name not in self.SUPPORTED_COLLECTION_BLOCKS
        )
        if unsupported:
            formatted = ", ".join(unsupported)
            raise ParseError(f"Unsupported collection sections in {path}: {formatted}")

    def _validate_folder_blocks(self, blocks: dict[str, str], path: Path) -> None:
        """Reject unsupported native `folder.bru` sections instead of ignoring them."""
        unsupported = sorted(
            block_name for block_name in blocks if block_name not in self.SUPPORTED_FOLDER_BLOCKS
        )
        if unsupported:
            formatted = ", ".join(unsupported)
            raise ParseError(f"Unsupported folder sections in {path}: {formatted}")

    def _validate_environment_blocks(self, blocks: dict[str, str], path: Path) -> None:
        """Reject unsupported native environment sections instead of ignoring them."""
        unsupported = sorted(
            block_name for block_name in blocks if block_name not in self.SUPPORTED_ENVIRONMENT_BLOCKS
        )
        if unsupported:
            formatted = ", ".join(unsupported)
            raise ParseError(f"Unsupported environment sections in {path}: {formatted}")

    def _merge_variables(
        self,
        collection_variables: list[BrunoVariable],
        environment_variables: list[BrunoVariable],
    ) -> list[BrunoVariable]:
        """Merge collection and environment variables with environment precedence."""
        merged: dict[str, BrunoVariable] = {}

        for variable in collection_variables:
            merged[variable.name] = variable

        for variable in environment_variables:
            merged[variable.name] = variable

        return list(merged.values())
