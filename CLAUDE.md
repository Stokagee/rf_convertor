# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bruno → Robot Framework converter. Transforms Bruno API collections (OpenCollection YAML/JSON) into executable Robot Framework `.robot` files using RequestsLibrary.

## Commands

```bash
# Install dependencies (development mode)
pip install -e ".[dev]"

# Run converter
bruno-to-robot -i collection.yaml -o tests/api.robot

# Run with verbose output
bruno-to-robot -i collection.yaml -o tests/ -v

# Dry run (show what would be generated)
bruno-to-robot -i collection.yaml -o tests/api.robot --dry-run

# Run tests
pytest

# Run specific test file
pytest tests/unit/test_parser.py -v

# Run with coverage
pytest --cov=bruno_to_robot --cov-report=html

# Type checking
mypy src/

# Linting
ruff check src/

# Format code
ruff format src/

# Validate generated .robot syntax (requires robotframework)
robot --dryrun examples/output/products.robot
```

## Architecture

```
src/bruno_to_robot/
├── cli.py                 # Click CLI entry point
├── parser/                # Input parsing (YAML/JSON → BrunoCollection)
│   ├── base.py           # Abstract parser interface
│   ├── yaml_parser.py    # OpenCollection YAML parser
│   └── json_parser.py    # JSON parser (delegates to yaml_parser logic)
├── models/                # Pydantic data models
│   ├── bruno.py          # BrunoCollection, BrunoRequest, BrunoHttp, etc.
│   └── robot.py          # RobotSuite, RobotTestCase, RobotStep, RobotVariable
├── mapper/                # Bruno → Robot transformation
│   ├── request_mapper.py # Main mapper: collection → test suites
│   ├── assertion_mapper.py # Chai assertions → Robot keywords
│   └── auth_mapper.py    # Auth config → session setup
├── generator/             # Jinja2 template rendering
│   └── robot_generator.py # RobotSuite → .robot file
└── templates/             # Jinja2 templates
    ├── test_suite.robot.jinja
    └── resource.robot.jinja
```

**Data flow:**
```
Input file → Parser → BrunoCollection → RequestMapper → RobotSuite → Generator → .robot file
```

## Key Design Decisions

### Headers Handling (CRITICAL)
- **NEVER** use fictional `Set Headers` keyword - it doesn't exist in RequestsLibrary
- Headers go to `*** Variables ***` as `&{DEFAULT_HEADERS}` dictionary
- Pass to requests: `GET On Session    alias    /path    headers=${DEFAULT_HEADERS}`
- Per-request headers are merged with defaults

### Session Management
- Suite-level session via `Suite Setup` (DRY, not per-test)
- Use `...On Session` keywords: `GET On Session`, `POST On Session`, etc.
- Session teardown: `Delete All Sessions`
- Session name configurable via `--session-name` (default: `api`)

### Variables
- Bruno `{{variable}}` → Robot `${VARIABLE}`
- Environment vars: `%{ENV_VAR}` syntax
- Secrets: NEVER hardcode - use `%{SECRET}` or placeholder with TODO comment
- Variables sorted alphabetically for idempotency

### Auth Types Supported
| Type | Implementation |
|------|---------------|
| Basic | `Create Session ... auth=${USER}:${PASS}` |
| Bearer | `Authorization: Bearer ${TOKEN}` in headers |
| API Key | Custom header or query param |
| OAuth 2.0 | Custom keyword (placeholder - needs implementation) |
| Client Cert | `Create Session ... cert=(${CERT}, ${KEY})` |
| Inherit | Uses collection-level auth |

### Assertion Conversion
- Simple Chai patterns auto-converted:
  - `expect(res.status).to.equal(200)` → `Should Be Equal As Integers ${resp.status_code} 200`
  - `expect(res.body.id).to.exist` → `Dictionary Should Contain Key ${resp.json()} id`
- Complex JS scripts → Comment placeholder `# TODO: Manual conversion`
- Patterns in `mapper/assertion_mapper.py`

### Idempotency
- Same input → identical output (byte-for-byte)
- Variables sorted alphabetically
- Test cases sorted by name
- Headers/params sorted by key
- Skip writing if content unchanged (preserves timestamps)

## Input Format (OpenCollection YAML)

```yaml
info:
  name: Create User
  type: http
  seq: 1
http:
  method: POST
  url: https://api.example.com/users
  body:
    type: json
    data: |-
      {"name": "John Doe", "email": "john@example.com"}
  auth: inherit
  headers:
    X-Custom: value
runtime:
  scripts:
    - type: tests
      code: |-
        test("should return 201", function() {
          expect(res.status).to.equal(201);
        });
```

## Generated Output Structure

```robotframework
*** Settings ***
Library           RequestsLibrary
Suite Setup       Create API Session
Suite Teardown    Delete All Sessions

*** Variables ***
${BASE_URL}           https://api.example.com
&{DEFAULT_HEADERS}    Content-Type=application/json    Accept=application/json

*** Keywords ***
Create API Session
    Create Session    api    ${BASE_URL}

*** Test Cases ***
Create User
    [Documentation]    Converted from Bruno request: Create User
    [Tags]    api    post
    ${body}=    Create Dictionary    name=John Doe    email=john@example.com
    ${resp}=    POST On Session    api    /users    json=${body}    headers=${DEFAULT_HEADERS}
    Should Be True    ${resp.status_code} < 400    Check for 2xx/3xx status
```

## Testing

- Fixtures in `tests/fixtures/` - sample Bruno collections
- Unit tests per module in `tests/unit/`
- Integration tests in `tests/integration/`
- Use `pytest` fixtures from `conftest.py`

## Dependencies

Core (installed by default):
- pydantic >= 2.5 (data validation)
- jinja2 >= 3.1 (templating)
- pyyaml >= 6.0 (YAML parsing)
- click >= 8.1 (CLI)

Dev (`pip install -e ".[dev]"`):
- pytest >= 8.0
- pytest-cov >= 4.1
- ruff >= 0.3
- mypy >= 1.8

Robot (`pip install -e ".[robot]"`):
- robotframework >= 7.0
- robotframework-requests >= 0.9.7

## Common Patterns

### Adding new assertion pattern
Edit `mapper/assertion_mapper.py`:
1. Add regex pattern to `_build_patterns()`
2. Create mapper function (e.g., `_map_new_pattern`)
3. Return `RobotStep` with appropriate keyword

### Adding new auth type
Edit `mapper/auth_mapper.py`:
1. Add `map_xxx_auth()` method
2. Return list of `RobotStep` for session setup
3. Add variable extraction to `get_auth_variables()`

### Modifying output format
Edit Jinja2 templates in `templates/`:
- `test_suite.robot.jinja` - main test file
- `resource.robot.jinja` - shared variables/keywords
