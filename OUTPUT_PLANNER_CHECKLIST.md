# Output Planner Checklist

## Goal

Introduce a generic output planner that supports arbitrary Bruno folder names and scales to
large collections without hardcoded assumptions.

## First Iteration Checklist

- [x] Add `bruno_to_robot.output_planner`
- [x] Define `SplitMode`
- [x] Define `LayoutRule`
- [x] Define `PlannedOutputFile`
- [x] Implement `plan_collection_outputs(collection, default_mode, rules)`
- [x] Support `single`
- [x] Support compatibility `top-folder`
- [x] Support `request-tree`
- [x] Support `flow-folder`
- [x] Keep routing rule evaluation ordered and deterministic
- [x] Use source relative paths as output identity
- [x] Use source filenames for output slugs
- [x] Preserve flow order by `seq`, then source path fallback
- [x] Expose `--split-mode` in CLI
- [x] Keep `--split` as backward-compatible alias
- [x] Add planner-only unit tests
- [x] Add CLI help unit test
- [x] Add cache follow-up tasks after planner lands

## Guardrails

- [x] No hardcoded folder names in production code
- [x] No output identity based only on display names
- [x] No flattening nested flow folders into parent suites
- [x] No alphabetical reordering of ordered flows
- [x] No output overwrite on slug collisions (deterministic hash fallback)

## Later Follow-Ups

- [x] Planner-driven cache scopes
- [x] Resource layering for shared variables (`--resource` imports in generated suites)
- [ ] Init layering for shared setup/keywords
- [x] Rename/move cleanup for nested output trees
- [x] Glob or predicate-based route matching
- [x] Optional user config file for route rules
