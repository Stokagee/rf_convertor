# Output Layout Proposal

## Context

The project can contain many top-level folders, many nested folders, and arbitrary folder names.
Some branches behave like endpoint catalogs, while others behave like ordered multi-step flows.

The current split model is `top-level folder -> one .robot suite`. That is too coarse for
large collections and does not distinguish between unordered request catalogs and ordered flow folders.

## Problems In The Current Layout

- Nested folders are flattened into the parent split suite.
- Output files are generated into a flat directory.
- Suite identity is tied to display names instead of stable source paths.
- Flow requests lose ordering because rendered test cases are sorted by name.
- Cache scope is aligned with top-level folders, not with request files or leaf flow folders.
- Helper/resource generation is suite-local, which will duplicate shared setup in fine-grained layouts.

## Recommended Target Model

Use a routing-based output planner between mapping and generation.

### Split Modes

- `single`
  - Whole collection -> one `.robot` file.
- `top-folder`
  - Current compatibility mode.
- `request-tree`
  - One Bruno request file -> one `.robot` file.
  - Output directory structure mirrors Bruno folder tree.
- `flow-folder`
  - One leaf flow folder -> one `.robot` file.
  - All requests inside the leaf folder become one ordered suite.

## Recommended Routing Model

- Default mode for large collections: `request-tree`
- Optional ordered rules can override the default for selected path prefixes or patterns
- Fallback for unspecified areas: `request-tree`

Important: the implementation must not hardcode special Bruno folder names such as `Flows`,
`External`, `E2E`, or similar. Folder names are data. Split strategy is configuration.

This gives:

- small, isolated endpoint suites for any branch that stays on `request-tree`
- ordered flow suites for any branch explicitly routed to `flow-folder`
- future folders can opt into a specific mode by rule instead of parser-specific heuristics

## Output Shape

Example Bruno tree:

```text
Third Party/
  Customer/
    Get Customer.bru
    Delete Customer.bru

Scenario Batch/
  Client API Flow/
    01 Create Client.bru
    02 Create Token.bru
    03 Get Profile.bru
```

Recommended output:

```text
robot/
  third_party/
    customer/
      get_customer.robot
      delete_customer.robot

  scenario_batch/
    client_api_flow.robot
```

For nested flow folders:

```text
Scenario Batch/
  Customer/
    Onboarding/
      01 Create Client.bru
      02 Verify Client.bru
    Negative/
      01 Missing Token.bru
```

Recommended output:

```text
robot/
  scenario_batch/
    customer/
      onboarding.robot
      negative.robot
```

Only folders that directly contain flow requests produce a `.robot` file.

## Planner Responsibilities

Add a dedicated planner layer, for example `bruno_to_robot.output_planner`.

Planner input:

- parsed `BrunoCollection`
- default split mode
- ordered path routing rules

Planner output:

- list of planned suite files
- relative output path for each suite
- source request paths belonging to each suite
- chosen split mode
- execution ordering policy
- cache scope identity

Suggested planner types:

- `SplitMode`
- `LayoutRule`
- `PlannedOutputFile`
- `plan_collection_outputs(...)`

`LayoutRule` should be generic enough to support arbitrary folder names. The minimal first version
can start with `path_prefix`, but the design should leave room for glob or predicate-based matching later.

## Important Behavioral Rules

### Request Tree

- one request file per output suite
- output path mirrors Bruno relative path
- file slug comes from source filename, not request display name
- root-level requests generate root-level suite files

### Flow Folder

- one leaf folder with request files -> one output suite
- request execution order must follow source order, not alphabetical suite rendering
- prefer `seq` when present
- fallback to filesystem/path order when `seq` is missing or duplicated

### Identity And Naming

- use source relative path as the primary identity
- use display name only for test/suite titles
- avoid output collisions by deriving path from source tree
- support slug+hash fallback for long or duplicate-safe filenames

## Required Model Changes

- decouple "test mapping" from "disk layout planning"
- extend Robot output metadata with:
  - `relative_output_path`
  - `resource_imports`
  - `preserve_test_order`
  - optional `source_paths`
- stop sorting flow test cases by display name when order matters

## Cache Changes

Current cache is top-folder oriented. New cache should support:

- `request-tree`: one cache scope per request file
- `flow-folder`: one cache scope per leaf flow folder
- shared fingerprint inputs:
  - collection/env files
  - build signature version
  - shared resource/helper content affecting the suite

## Recommended Implementation Order

1. Add planner API and tests without changing production behavior.
2. Add `--split-mode` CLI option and keep `--split` as a compatibility alias.
3. Implement planner in compatibility mode only (`single`, `top-folder`).
4. Implement `request-tree`.
5. Implement `flow-folder`.
6. Move shared setup/variables into resource/init layers where duplication becomes too high.
7. Rework cache to align with planner outputs.

## Test Strategy

Unit tests first:

- planner applies `request-tree` to arbitrary folder names by default
- planner routes any matching branch to `flow-folder` through explicit rules
- request-tree mirrors nested directories
- flow-folder emits one suite per leaf flow folder
- flow-folder preserves request order
- duplicate request names in different folders remain collision-free
- CLI help exposes `--split-mode`

Only after that should generator and CLI implementation change.
