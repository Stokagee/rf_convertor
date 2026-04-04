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
# Convert a Bruno collection
bruno-to-robot -i collection.yaml -o tests/api.robot

# Convert with split output (one file per folder)
bruno-to-robot -i collection.yaml -o tests/ --split

# Convert with separate resource file
bruno-to-robot -i collection.yaml -o tests/api.robot --resource resources/variables.robot
```

## Input Formats

Supports Bruno export formats:

- **OpenCollection YAML** (recommended) - most structured
- **Bruno JSON export** - standard JSON format
- **Postman JSON** - compatible format

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
| OAuth 2.0 | Custom keyword (placeholder) |
| Client Certificate | `Create Session ... cert=(${CERT}, ${KEY})` |

**Important:** Secrets are never hardcoded. Use environment variables or Robot variable files.

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
  -i, --input PATH         Bruno collection file (YAML or JSON) [required]
  -o, --output PATH        Output .robot file or directory [required]
  --format [json|yaml]     Force input format (auto-detected by default)
  --session-name NAME      Session name (default: api)
  --base-url URL           Override base URL from collection
  --split / --no-split     Split into multiple .robot files per folder
  --resource PATH          Generate separate resource file for variables
  --dry-run                Show what would be generated without writing
  -v, --verbose            Increase verbosity
  -q, --quiet              Only show errors
  --version                Show version
  --help                   Show this message
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
├── cli.py           # Click CLI entry point
├── parser/          # YAML/JSON parsing
├── models/          # Pydantic data models
├── mapper/          # Bruno → Robot transformation
├── generator/       # Jinja2 template rendering
└── templates/       # .robot Jinja2 templates

tests/
├── fixtures/        # Sample Bruno collections
├── unit/            # Unit tests per module
└── integration/     # Full pipeline tests
```

## License

MIT
