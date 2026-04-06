"""Map Bruno runtime scripts to Robot Framework keywords and Python helpers."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from bruno_to_robot.models.bruno import BrunoRequest, BrunoRuntime, BrunoScript

logger = logging.getLogger(__name__)


@dataclass
class ExtractedVariable:
    """Variable extracted from after-response script."""

    name: str  # Robot variable name (UPPER_CASE)
    json_path: str  # JSON path like "access_token" or "data.id"
    original_js: str  # Original JS code for reference


@dataclass
class PreRequestHelper:
    """Generated Python helper for pre-request script."""

    function_name: str
    python_code: str
    original_js: str
    requires_imports: list[str] = field(default_factory=list)


@dataclass
class ScriptMappingResult:
    """Result of mapping Bruno scripts to Robot/Python."""

    pre_request_helper: PreRequestHelper | None = None
    extracted_variables: list[ExtractedVariable] = field(default_factory=list)
    rf_steps_before: list[str] = field(default_factory=list)  # Robot keyword calls
    rf_steps_after: list[str] = field(default_factory=list)  # Variable extraction steps


class ScriptMapper:
    """Maps Bruno runtime scripts to Robot Framework and Python."""

    # Pattern for bru.setEnvVar('var_name', res.body.field)
    SET_ENV_VAR_PATTERN = re.compile(
        r"bru\.setEnvVar\s*\(\s*['\"](\w+)['\"]\s*,\s*res\.body(?:\.(\w+))*\s*\)"
    )

    # Pattern for bru.setEnvVar with nested access
    SET_ENV_VAR_NESTED_PATTERN = re.compile(
        r"bru\.setEnvVar\s*\(\s*['\"](\w+)['\"]\s*,\s*res\.body\.([\w.]+)\s*\)"
    )

    # Pattern for req.setBody(JSON.stringify(body))
    SET_BODY_PATTERN = re.compile(r"req\.setBody\s*\(\s*JSON\.stringify\s*\(\s*(\w+)\s*\)\s*\)")

    def map_scripts(self, request: BrunoRequest) -> ScriptMappingResult:
        """Map all runtime scripts for a request.

        Args:
            request: Bruno request with optional runtime scripts

        Returns:
            ScriptMappingResult with helpers and RF steps
        """
        result = ScriptMappingResult()

        if not request.runtime or not request.runtime.scripts:
            return result

        for script in request.runtime.scripts:
            if script.type in ("before-request", "pre-request"):
                helper = self._map_before_request(script, request.name)
                if helper:
                    result.pre_request_helper = helper
                    result.rf_steps_before.append(f"${{body}}=    {helper.function_name}")

            elif script.type in ("after-response", "post-request"):
                variables = self._extract_env_vars(script.code)
                result.extracted_variables.extend(variables)
                for var in variables:
                    result.rf_steps_after.append(
                        f"${{json}}=    Set Variable    ${{resp.json()}}\n"
                        f"${{{var.name}}}=    Get From Dictionary    ${{json}}    {var.json_path}\n"
                        f"Set Suite Variable    ${{{var.name}}}    ${{{var.name}}}"
                    )

        return result

    def _map_before_request(self, script: BrunoScript, request_name: str) -> PreRequestHelper | None:
        """Map before-request script to Python helper function.

        Detects common patterns and generates Python code.
        Unknown patterns get a TODO with original JS.
        """
        code = script.code

        # Check for random data generator pattern
        if self._is_random_data_generator(code):
            return self._generate_random_data_helper(code, request_name)

        # Check for simple body construction
        if self._is_simple_body_construction(code):
            return self._generate_simple_body_helper(code, request_name)

        # Unknown pattern - create placeholder
        return self._generate_placeholder_helper(code, request_name)

    def _is_random_data_generator(self, code: str) -> bool:
        """Check if script is a random data generator."""
        patterns = [
            r"function\s+randomItem",
            r"function\s+randomPhone",
            r"function\s+randomName",
            r"Math\.random\(\)",
            r"Math\.floor",
        ]
        return any(re.search(p, code) for p in patterns)

    def _is_simple_body_construction(self, code: str) -> bool:
        """Check if script just constructs a simple body."""
        return "req.setBody" in code and not self._is_random_data_generator(code)

    def _generate_random_data_helper(self, code: str, request_name: str) -> PreRequestHelper:
        """Generate Python helper for random data generation."""
        func_name = self._make_function_name(request_name)

        python_code = f'''def {func_name}():
    """Generate request body for {request_name}.

    Auto-converted from Bruno before-request script.
    """
    import random
    import time

    first_names = ['Jan', 'Petr', 'Lucie', 'Eva', 'Tomas', 'Marie', 'David']
    last_names = ['Novak', 'Svoboda', 'Novotny', 'Dvorak', 'Cerny']
    streets = ['Narodni', 'Vinohradska', 'Dlouha', 'Masarykova', 'Vaclavske namesti']
    cities = ['Praha 1', 'Praha 2', 'Praha 3', 'Praha 4']
    domains = ['example.cz', 'mail.cz', 'seznam.cz']
    tags = ['bike', 'car', 'vip', 'express', 'fragile_ok']

    def random_item(arr):
        return random.choice(arr)

    def random_phone():
        return "+420" + str(random.randint(100000000, 999999999))

    def random_name():
        return f"{{random_item(first_names)}} {{random_item(last_names)}}"

    def random_address():
        return f"{{random_item(streets)}} {{random.randint(1, 200)}}, {{random_item(cities)}}"

    def random_coords(base_lat, base_lng, delta):
        lat = round(base_lat + (random.random() * 2 - 1) * delta, 6)
        lng = round(base_lng + (random.random() * 2 - 1) * delta, 6)
        return {{"lat": lat, "lng": lng}}

    timestamp = int(time.time())

    # Generate body based on detected patterns
    # TODO: Customize body structure based on actual request needs
    body = {{
        "email": f"test{{timestamp}}@test.cz",
        "name": random_name(),
        "phone": random_phone(),
    }}

    return body
'''
        return PreRequestHelper(
            function_name=func_name,
            python_code=python_code,
            original_js=code,
            requires_imports=["random", "time"],
        )

    def _generate_simple_body_helper(self, code: str, request_name: str) -> PreRequestHelper:
        """Generate Python helper for simple body construction."""
        func_name = self._make_function_name(request_name)

        # Try to extract body from req.setBody(JSON.stringify(body))
        body_match = self.SET_BODY_PATTERN.search(code)
        body_var = body_match.group(1) if body_match else "body"

        python_code = f'''def {func_name}():
    """Generate request body for {request_name}.

    Auto-converted from Bruno before-request script.
    Original JS:
    {code}
    """
    # TODO: Implement body generation
    body = {{}}
    return body
'''
        return PreRequestHelper(
            function_name=func_name,
            python_code=python_code,
            original_js=code,
            requires_imports=[],
        )

    def _generate_placeholder_helper(self, code: str, request_name: str) -> PreRequestHelper:
        """Generate placeholder helper for unknown script patterns."""
        func_name = self._make_function_name(request_name)

        python_code = f'''def {func_name}():
    """Generate request body for {request_name}.

    TODO: Manual conversion required.
    Original Bruno script:
    ```
    {code}
    ```
    """
    # Placeholder - implement based on original script
    raise NotImplementedError("Manual conversion of pre-request script required")
'''
        return PreRequestHelper(
            function_name=func_name,
            python_code=python_code,
            original_js=code,
            requires_imports=[],
        )

    def _extract_env_vars(self, code: str) -> list[ExtractedVariable]:
        """Extract bru.setEnvVar calls from after-response script."""
        variables = []

        # Match simple patterns: bru.setEnvVar('var', res.body.field)
        for match in self.SET_ENV_VAR_NESTED_PATTERN.finditer(code):
            var_name = match.group(1).upper()  # Convert to UPPER_CASE
            json_path = match.group(2)
            original_js = match.group(0)

            variables.append(ExtractedVariable(
                name=var_name,
                json_path=json_path,
                original_js=original_js,
            ))

        return variables

    def _make_function_name(self, request_name: str) -> str:
        """Convert request name to valid Python function name."""
        # Remove special chars, convert to snake_case
        clean = re.sub(r"[^a-zA-Z0-9\s]", "", request_name)
        words = clean.lower().split()
        return "generate_" + "_".join(words) + "_body"


def generate_helpers_file(helpers: list[PreRequestHelper], suite_name: str) -> str:
    """Generate complete Python helpers file content.

    Args:
        helpers: List of pre-request helpers
        suite_name: Name of the Robot suite (for file naming)

    Returns:
        Complete Python file content
    """
    lines = [
        '"""Robot Framework helper library for request body generation.',
        "",
        f"Auto-generated by bruno-to-robot converter.",
        "Customize as needed for your test environment.",
        '"""',
        "",
        "import random",
        "import time",
        "",
        "",
    ]

    for helper in helpers:
        lines.append(helper.python_code)
        lines.append("")
        lines.append("")

    return "\n".join(lines)
