# Bruno to Robot Framework Converter

Convert Bruno API collections to Robot Framework test suites using RequestsLibrary.

## Installation

```bash
pip install bruno-to-robot
```

Or install from source:

```bash
git clone https://github.com/Stokagee/rf_convertor
cd bruno-to-robot
pip install -e ".[dev]"
```

## Quick Start

```bash
# Convert an OpenCollection YAML export
bruno-to-robot -i collection.yaml -o tests/api.robot

# Convert a Bruno directory directly
bruno-to-robot -i ./my-bruno-collection -o tests/ --env test_client --split

# Generate one .robot per Bruno request path
bruno-to-robot -i ./my-bruno-collection -o tests/ --env test_client --split-mode request-tree

# Generate request-tree output with shared keywords/init layering
bruno-to-robot -i ./my-bruno-collection -o tests/ --env test_client --split-mode request-tree --init-layering

# Convert a single `.bru` request
bruno-to-robot -i "requests/Get Health.bru" -o tests/health.robot

# Convert with separate resource file
bruno-to-robot -i collection.yaml -o tests/api.robot --resource resources/variables.robot
```

When `--resource` is used, generated suites import that file and shared variables are moved out of per-suite `*** Variables ***` blocks.

## Input Formats

Supports these inputs:

- **OpenCollection YAML** via `.yaml` / `.yml`
- **OpenCollection JSON** via `.json`
- **Direct Bruno request** via single `.bru`
- **Direct Bruno collection directory** with request `.bru` files, optional `collection.bru`, `folder.bru`, `environments/*.bru`, and optional `bruno.json`

## Direct Bruno Support

Direct Bruno parsing is intentionally MVP-scoped. The current `.bru` support covers:

- `meta/name`
- HTTP method blocks like `get {}` or `post {}`
- `url`
- `headers`
- `params:query`
- `body:*`
- `auth:*` subset needed by the current mapper
- collection variables from `collection.bru` via `vars:pre-request`
- folder metadata from `folder.bru`
- folder structure derived from the filesystem
- environment selection from `environments/*.bru` via `--env`
- disabled native Bruno variables prefixed with `~` are ignored
- JSON or docs content with `{}` inside string literals is parsed safely

Current out-of-scope or partial areas:

- full native Bruno parity
- inheritance semantics beyond the selected env file
- scripts and assertions from direct `.bru` input are rejected fail-fast
- advanced auth flows in native `.bru` format
- full Bruno metadata coverage
- local native Bruno variables prefixed with `@` are rejected fail-fast
- unsupported sections in `collection.bru`, `folder.bru`, or `environments/*.bru` are rejected fail-fast
- disabled and duplicate header or param semantics

## Environment Selection

If your source defines multiple Bruno environments, you can select exactly one:

```bash
bruno-to-robot -i ./my-bruno-collection -o tests/ --env test_client
```

The selected environment affects collection variables, derived `BASE_URL`, and split-build cache invalidation.

For native Bruno directories:

- `vars {}` from the selected `environments/<name>.bru` file are applied
- `~disabledVar` entries are skipped
- `@localVar` entries are not currently supported and stop the parse with an error

## Split Build Cache

When the input is a Bruno directory and `--split` is enabled, the converter keeps a small manifest in the output directory and reuses unchanged suite outputs on the next run.

The cache invalidates when:

- a `.bru` request changes inside a tracked top-level folder
- a root-level `.bru` request changes
- the selected environment name changes
- the selected environment file content changes
- `bruno.json` changes
- `collection.bru` changes
- `--base-url`, `--session-name`, or other build options change
- the converter build signature version changes

Stale split outputs are also removed when the corresponding top-level folder or root request suite disappears.

## Output Layout Planning

For large Bruno collections you can choose how suites are split:

- `--split-mode single` - one output suite
- `--split-mode top-folder` - legacy `--split` behavior
- `--split-mode request-tree` - one request file -> one `.robot` file
- `--split-mode flow-folder` - one leaf flow folder -> one ordered `.robot` suite

Route specific branches to a different mode:

```bash
bruno-to-robot -i ./my-bruno-collection -o tests/ --env test_client \
  --split-mode request-tree \
  --layout-rule "Flows=flow-folder"
```

`--layout-rule` accepts both plain path-prefix rules and wildcard patterns (for example `Flows/*=flow-folder`). Rule matching is case-insensitive.

Or load rules from config:

```bash
bruno-to-robot -i ./my-bruno-collection -o tests/ --env test_client --layout-config layout.yaml
```

If `--layout-config` is omitted and the input is a Bruno directory, the CLI auto-loads the first existing file from:

- `bruno-to-robot.layout.yaml`
- `bruno-to-robot.layout.yml`
- `.bruno-to-robot.layout.yaml`
- `.bruno-to-robot.layout.yml`

Tip: combine request-tree output with `--resource` to keep many small suites lightweight while sharing one variables file.

`--init-layering` adds a shared keyword resource (`_shared/common_keywords.robot`) and root `__init__.robot`, then removes duplicated `*** Keywords ***` sections from generated suite files.

## Output Structure

Generated `.robot` files follow Robot Framework best practices:

```robotframework
*** Settings ***
Library           RequestsLibrary
Suite Setup       Create API Session
Suite Teardown    Delete All Sessions

*** Variables ***
${BASE_URL}           https://api.example.com
&{DEFAULT_HEADERS}    Content-Type=application/json    Accept=application/json

*** Test Cases ***
Get Users
    ${resp}=    GET On Session    api    /users    headers=${DEFAULT_HEADERS}
    Status Should Be    ${resp}    200
```

## Authentication Support

| Bruno Auth Type | Robot Framework Implementation |
|-----------------|-------------------------------|
| Basic Auth | `Create Session ... auth=${USER}:${PASS}` |
| Bearer Token | `Authorization: Bearer ${TOKEN}` header |
| API Key | Custom header or query param |
| OAuth 2.0 | Custom keyword flow |
| Client Certificate | `Create Session ... cert=(${CERT}, ${KEY})` |

Important: secrets are never hardcoded. Use environment variables or Robot variable files.

## Assertion Conversion

Basic Chai assertions are automatically converted:

| Bruno (Chai) | Robot Framework |
|--------------|-----------------|
| `expect(res.status).to.equal(200)` | `Should Be Equal As Integers ${resp.status_code} 200` |
| `expect(res.body.id).to.exist` | `Dictionary Should Contain Key ${resp.json()} id` |
| `expect(res.body.name).to.contain("John")` | `Should Contain ${resp.json()["name"]} John` |

Complex scripts require manual conversion and are marked with TODO comments.

## CLI Options

```
Usage: bruno-to-robot [OPTIONS]

Options:
  -i, --input PATH          Path to Bruno collection file, Bruno request, or
                            Bruno collection directory [required]
  -o, --output PATH         Path to output .robot file or directory [required]
  --format [bru|json|yaml]  Force input format (auto-detected by default)
  --session-name TEXT       Name for the RequestsLibrary session (default: api)
  --base-url TEXT           Override base URL from collection
  --env TEXT                Select a named Bruno environment
  --split / --no-split      Split into multiple .robot files per folder
  --split-mode [single|top-folder|request-tree|flow-folder]
                            Output layout mode for generated .robot files
  --layout-rule TEXT        Route one source path prefix to a split mode
                            using PATH_PREFIX=SPLIT_MODE
  --layout-config PATH      Load default split mode and layout rules from a
                            YAML config file
  --resource PATH           Generate separate resource file for variables
  --init-layering / --no-init-layering
                            Generate shared keyword resource and __init__.robot
                            for split layouts
  --dry-run                 Show what would be generated without writing files
  -v, --verbose             Increase verbosity (can be used multiple times)
  -q, --quiet               Decrease verbosity (only errors)
  --version                 Show version
  --help                    Show this message and exit
```

## Windows Note

If your environment has an unreliable system temp directory, certificate conversion can be pointed to a known writable directory with:

```powershell
$env:BRUNO_TO_ROBOT_TEMP_DIR = "C:\work\rf-temp"
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=bruno_to_robot

# Type checking
mypy src/

# Linting
ruff check src/

# Format
ruff format src/
```

## Project Structure

```
src/bruno_to_robot/
|-- cli.py           # Click CLI entry point
|-- parser/          # YAML/JSON/.bru parsing
|-- models/          # Pydantic data models
|-- mapper/          # Bruno -> Robot transformation
|-- generator/       # Jinja2 template rendering
|-- library/         # Runtime helpers for OAuth2 and certificates
`-- templates/       # .robot and helper templates

tests/
|-- fixtures/        # Sample Bruno collections
|-- unit/            # Unit tests per module
`-- integration/     # Full pipeline tests
```

## License

MIT
