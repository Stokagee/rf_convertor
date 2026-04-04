"""Map Bruno assertions to Robot Framework keywords."""

from __future__ import annotations

import re

from bruno_to_robot.models.robot import RobotStep

# Mapping of Chai assertion methods to Robot Framework keywords
ASSERTION_KEYWORDS = {
    "equal": "Should Be Equal",
    "eql": "Should Be Equal",
    "deep.equal": "Should Be Equal",
    "not.equal": "Should Not Be Equal",
    "exist": "Should Not Be Empty",
    "not.exist": "Should Be Empty",
    "true": "Should Be True",
    "false": "Should Be False",
    "null": "Should Be Equal",
    "undefined": "Should Be Equal",
    "above": "Should Be True",
    "below": "Should Be True",
    "least": "Should Be True",
    "most": "Should Be True",
    "within": "Should Be True",
    "instanceof": "Should Be Instance Of",
    "match": "Should Match Regexp",
    "string": "Should Be String",
    "number": "Should Be Number",
    "array": "Should Be List",
    "object": "Should Be Dictionary",
    "contain": "Should Contain",
    "not.contain": "Should Not Contain",
    "length": "Length Should Be",
    "have.property": "Dictionary Should Contain Key",
    "have.key": "Dictionary Should Contain Key",
    "have.keys": "Dictionary Should Contain Key",
}


class AssertionMapper:
    """Maps Bruno/Chai assertions to Robot Framework keywords."""

    def __init__(self) -> None:
        self._patterns = self._build_patterns()

    def _build_patterns(self) -> list[tuple[re.Pattern, callable]]:
        """Build regex patterns for assertion detection."""
        return [
            # Status code assertions
            (
                re.compile(
                    r"expect\s*\(\s*res(?:ponse)?\.status(?:_?code)?\s*\)"
                    r"\s*\.\s*to\s*\.\s*(?:equal|eql)\s*\(\s*(\d+)\s*\)"
                ),
                self._map_status_equal,
            ),
            # Response body property equal
            (
                re.compile(
                    r"expect\s*\(\s*res(?:ponse)?\.body\.(\w+(?:\.\w+)*)\s*\)"
                    r"\s*\.\s*to\s*\.\s*(?:equal|eql)\s*\(\s*['\"]?([^)'\"]*)['\"]?\s*\)"
                ),
                self._map_body_equal,
            ),
            # Response body property exist
            (
                re.compile(
                    r"expect\s*\(\s*res(?:ponse)?\.body\.(\w+(?:\.\w+)*)\s*\)"
                    r"\s*\.\s*to\s*\.\s*exist\s*\)?"
                ),
                self._map_body_exist,
            ),
            # Response body property contain
            (
                re.compile(
                    r"expect\s*\(\s*res(?:ponse)?\.body\.(\w+(?:\.\w+)*)\s*\)"
                    r"\s*\.\s*to\s*\.\s*contain\s*\(\s*['\"]([^'\"]*)['\"]\s*\)"
                ),
                self._map_body_contain,
            ),
            # Response time assertions
            (
                re.compile(
                    r"expect\s*\(\s*res(?:ponse)?Time\s*\)"
                    r"\s*\.\s*to\s*\.\s*(?:be\s*\.)?(below|above|least|most)\s*\(\s*(\d+)\s*\)"
                ),
                self._map_response_time,
            ),
            # Header assertions
            (
                re.compile(
                    r"expect\s*\(\s*res(?:ponse)?\.headers?\s*\[\s*['\"]([^'\"]+)['\"]\s*\]\s*\)"
                    r"\s*\.\s*to\s*\.\s*(contain|equal|match)\s*\(\s*['\"]([^'\"]*)['\"]\s*\)"
                ),
                self._map_header,
            ),
        ]

    def parse_script(self, code: str) -> list[RobotStep]:
        """Parse assertion script and return Robot steps.

        Args:
            code: JavaScript/Chai assertion code

        Returns:
            List of RobotStep objects for assertions
        """
        steps = []

        for pattern, mapper in self._patterns:
            for match in pattern.finditer(code):
                try:
                    step = mapper(match)
                    if step:
                        steps.append(step)
                except (ValueError, IndexError):
                    # Skip unparseable assertions
                    continue

        # If no assertions were parsed, add a comment
        if not steps and code.strip():
            steps.append(
                RobotStep(
                    keyword="Log",
                    args=["WARNING: Could not auto-convert assertion"],
                    comment=f"Original: {code[:100]}...",
                )
            )

        return steps

    def _map_status_equal(self, match: re.Match) -> RobotStep:
        """Map status code equality assertion."""
        status = match.group(1)
        return RobotStep(
            keyword="Should Be Equal As Integers",
            args=["${resp.status_code}", status],
        )

    def _map_body_equal(self, match: re.Match) -> RobotStep:
        """Map body property equality assertion."""
        prop_path = match.group(1)
        expected = match.group(2)

        # Build the Robot variable path
        robot_path = self._build_json_path(prop_path)

        # Determine if expected is a number or string
        try:
            expected_val = int(expected)
            return RobotStep(
                keyword="Should Be Equal As Integers",
                args=[robot_path, str(expected_val)],
            )
        except ValueError:
            try:
                expected_val = float(expected)
                return RobotStep(
                    keyword="Should Be Equal As Numbers",
                    args=[robot_path, str(expected_val)],
                )
            except ValueError:
                return RobotStep(
                    keyword="Should Be Equal",
                    args=[robot_path, f"'{expected}'"],
                )

    def _map_body_exist(self, match: re.Match) -> RobotStep:
        """Map body property existence assertion."""
        prop_path = match.group(1)

        return RobotStep(
            keyword="Dictionary Should Contain Key",
            args=["${resp.json()}", f"'{prop_path.split('.')[-1]}'"],
        )

    def _map_body_contain(self, match: re.Match) -> RobotStep:
        """Map body property contains assertion."""
        prop_path = match.group(1)
        expected = match.group(2)
        robot_path = self._build_json_path(prop_path)

        return RobotStep(
            keyword="Should Contain",
            args=[robot_path, f"'{expected}'"],
        )

    def _map_response_time(self, match: re.Match) -> RobotStep:
        """Map response time assertion."""
        comparator = match.group(1)
        threshold = int(match.group(2))

        if comparator == "below":
            condition = f"${{resp.elapsed.total_seconds()}} < {threshold / 1000}"
        elif comparator == "above":
            condition = f"${{resp.elapsed.total_seconds()}} > {threshold / 1000}"
        elif comparator == "least":
            condition = f"${{resp.elapsed.total_seconds()}} >= {threshold / 1000}"
        elif comparator == "most":
            condition = f"${{resp.elapsed.total_seconds()}} <= {threshold / 1000}"
        else:
            condition = f"${{resp.elapsed.total_seconds()}} < {threshold / 1000}"

        return RobotStep(
            keyword="Should Be True",
            args=[condition, f"Response time check ({comparator} {threshold}ms)"],
        )

    def _map_header(self, match: re.Match) -> RobotStep:
        """Map header assertion."""
        header_name = match.group(1)
        assertion_type = match.group(2)
        expected = match.group(3)

        if assertion_type == "contain":
            return RobotStep(
                keyword="Should Contain",
                args=[f"${{resp.headers['{header_name}']}}", f"'{expected}'"],
            )
        elif assertion_type == "match":
            return RobotStep(
                keyword="Should Match Regexp",
                args=[f"${{resp.headers['{header_name}']}}", expected],
            )
        else:
            return RobotStep(
                keyword="Should Be Equal",
                args=[f"${{resp.headers['{header_name}']}}", f"'{expected}'"],
            )

    def _build_json_path(self, prop_path: str) -> str:
        """Build Robot Framework JSON path from property path.

        user.address.city → ${resp.json()['user']['address']['city']}
        """
        parts = prop_path.split(".")
        if len(parts) == 1:
            return f"${{resp.json()['{parts[0]}']}}"

        path_parts = "][".join(f"'{p}'" for p in parts)
        return f"${{resp.json()[{path_parts}]}}"
