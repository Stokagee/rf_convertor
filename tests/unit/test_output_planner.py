"""Unit tests for future output layout planning."""

import importlib
from pathlib import Path

import pytest

from bruno_to_robot.models.bruno import BrunoCollection, BrunoFolder, BrunoHttp, BrunoRequest


def _load_planner_api():
    """Load the future output planner API and fail clearly while it is missing."""
    try:
        module = importlib.import_module("bruno_to_robot.output_planner")
    except ModuleNotFoundError:
        pytest.fail(
            "Missing output planner module 'bruno_to_robot.output_planner'. "
            "Implement the planner API before enabling new split modes."
        )

    required = ("SplitMode", "LayoutRule", "plan_collection_outputs")
    missing = [name for name in required if not hasattr(module, name)]
    if missing:
        pytest.fail(f"Missing output planner API members: {', '.join(missing)}")

    return module.SplitMode, module.LayoutRule, module.plan_collection_outputs


def _request(name: str, relative_path: str, seq: int = 1) -> BrunoRequest:
    """Create a minimal Bruno request for output planning tests."""
    return BrunoRequest(
        name=name,
        seq=seq,
        http=BrunoHttp(method="GET", url=f"https://api.example.com/{seq}"),
        path=relative_path,
    )


def _plan_by_relative_path(plans, relative_path: str):
    """Find one planned output file by relative path."""
    for plan in plans:
        if Path(plan.relative_output_path) == Path(relative_path):
            return plan
    pytest.fail(f"Missing planned output for {relative_path}")


class TestOutputPlanner:
    """Tests for future request-tree and flow-folder planning."""

    def test_request_tree_creates_one_output_file_per_request_and_mirrors_tree(self):
        """Request-tree mode should mirror nested Bruno paths into `.robot` files."""
        split_mode, layout_rule, plan_collection_outputs = _load_planner_api()

        collection = BrunoCollection(
            name="Paymont",
            requests=[_request("Health Check", "Health Check.bru")],
            folders=[
                BrunoFolder(
                    name="Third Party",
                    path="Third Party",
                    folders=[
                        BrunoFolder(
                            name="Customer",
                            path="Third Party/Customer",
                            requests=[
                                _request("Get Customer", "Third Party/Customer/Get Customer.bru"),
                                _request(
                                    "Delete Customer",
                                    "Third Party/Customer/Delete Customer.bru",
                                ),
                            ],
                        )
                    ],
                )
            ],
        )

        plans = plan_collection_outputs(
            collection,
            default_mode=split_mode.REQUEST_TREE,
            rules=[],
        )

        paths = [Path(plan.relative_output_path) for plan in plans]
        assert paths == sorted(paths)
        assert paths == [
            Path("health_check.robot"),
            Path("third_party/customer/delete_customer.robot"),
            Path("third_party/customer/get_customer.robot"),
        ]

        health_plan = _plan_by_relative_path(plans, "health_check.robot")
        assert health_plan.mode == split_mode.REQUEST_TREE
        assert health_plan.request_paths == ["Health Check.bru"]
        assert health_plan.preserve_test_order is False

    def test_default_request_tree_applies_without_folder_name_magic(self):
        """Any arbitrary branch should stay on request-tree unless a rule overrides it."""
        split_mode, layout_rule, plan_collection_outputs = _load_planner_api()

        collection = BrunoCollection(
            name="Paymont",
            folders=[
                BrunoFolder(
                    name="Whatever Name",
                    path="Whatever Name",
                    folders=[
                        BrunoFolder(
                            name="Odd Branch 7",
                            path="Whatever Name/Odd Branch 7",
                            requests=[
                                _request(
                                    "Fetch Widget",
                                    "Whatever Name/Odd Branch 7/Fetch Widget.bru",
                                ),
                            ],
                        )
                    ],
                )
            ],
        )

        plans = plan_collection_outputs(
            collection,
            default_mode=split_mode.REQUEST_TREE,
            rules=[],
        )

        plan = _plan_by_relative_path(plans, "whatever_name/odd_branch_7/fetch_widget.robot")
        assert plan.mode == split_mode.REQUEST_TREE
        assert plan.request_paths == ["Whatever Name/Odd Branch 7/Fetch Widget.bru"]

    def test_path_rules_route_arbitrary_branch_to_flow_folder_mode(self):
        """Ordered branches should use explicit routing rules, not hardcoded folder names."""
        split_mode, layout_rule, plan_collection_outputs = _load_planner_api()

        collection = BrunoCollection(
            name="Paymont",
            folders=[
                BrunoFolder(
                    name="Service Area",
                    path="Service Area",
                    folders=[
                        BrunoFolder(
                            name="Customer",
                            path="Service Area/Customer",
                            requests=[
                                _request("Get Customer", "Service Area/Customer/Get Customer.bru"),
                            ],
                        )
                    ],
                ),
                BrunoFolder(
                    name="Scenario Batch",
                    path="Scenario Batch",
                    folders=[
                        BrunoFolder(
                            name="Client API Flow",
                            path="Scenario Batch/Client API Flow",
                            requests=[
                                _request(
                                    "Create Client",
                                    "Scenario Batch/Client API Flow/01 Create Client.bru",
                                    seq=1,
                                ),
                                _request(
                                    "Create Token",
                                    "Scenario Batch/Client API Flow/02 Create Token.bru",
                                    seq=2,
                                ),
                                _request(
                                    "Get Profile",
                                    "Scenario Batch/Client API Flow/03 Get Profile.bru",
                                    seq=3,
                                ),
                            ],
                        )
                    ],
                ),
            ],
        )

        plans = plan_collection_outputs(
            collection,
            default_mode=split_mode.REQUEST_TREE,
            rules=[
                layout_rule(path_prefix="Scenario Batch", mode=split_mode.FLOW_FOLDER),
                layout_rule(path_prefix="Service Area", mode=split_mode.REQUEST_TREE),
            ],
        )

        flow_plan = _plan_by_relative_path(plans, "scenario_batch/client_api_flow.robot")
        assert flow_plan.mode == split_mode.FLOW_FOLDER
        assert flow_plan.request_paths == [
            "Scenario Batch/Client API Flow/01 Create Client.bru",
            "Scenario Batch/Client API Flow/02 Create Token.bru",
            "Scenario Batch/Client API Flow/03 Get Profile.bru",
        ]
        assert flow_plan.preserve_test_order is True

        external_plan = _plan_by_relative_path(plans, "service_area/customer/get_customer.robot")
        assert external_plan.mode == split_mode.REQUEST_TREE
        assert external_plan.request_paths == ["Service Area/Customer/Get Customer.bru"]

    def test_nested_flow_folders_emit_one_output_per_leaf_folder(self):
        """Only leaf folders matched by a flow rule should become output suites."""
        split_mode, layout_rule, plan_collection_outputs = _load_planner_api()

        collection = BrunoCollection(
            name="Paymont",
            folders=[
                BrunoFolder(
                    name="Scenario Batch",
                    path="Scenario Batch",
                    folders=[
                        BrunoFolder(
                            name="Customer",
                            path="Scenario Batch/Customer",
                            folders=[
                                BrunoFolder(
                                    name="Onboarding",
                                    path="Scenario Batch/Customer/Onboarding",
                                    requests=[
                                        _request(
                                            "Create Client",
                                            "Scenario Batch/Customer/Onboarding/01 Create Client.bru",
                                            seq=1,
                                        ),
                                        _request(
                                            "Verify Client",
                                            "Scenario Batch/Customer/Onboarding/02 Verify Client.bru",
                                            seq=2,
                                        ),
                                    ],
                                ),
                                BrunoFolder(
                                    name="Negative",
                                    path="Scenario Batch/Customer/Negative",
                                    requests=[
                                        _request(
                                            "Missing Token",
                                            "Scenario Batch/Customer/Negative/01 Missing Token.bru",
                                            seq=1,
                                        ),
                                    ],
                                ),
                            ],
                        )
                    ],
                )
            ],
        )

        plans = plan_collection_outputs(
            collection,
            default_mode=split_mode.REQUEST_TREE,
            rules=[layout_rule(path_prefix="Scenario Batch", mode=split_mode.FLOW_FOLDER)],
        )

        planned_paths = {Path(plan.relative_output_path) for plan in plans}
        assert planned_paths == {
            Path("scenario_batch/customer/onboarding.robot"),
            Path("scenario_batch/customer/negative.robot"),
        }

    def test_request_tree_paths_are_collision_free_for_duplicate_request_names(self):
        """Different source folders should keep duplicate request names collision-free."""
        split_mode, layout_rule, plan_collection_outputs = _load_planner_api()

        collection = BrunoCollection(
            name="Paymont",
            folders=[
                BrunoFolder(
                    name="Partner Edge",
                    path="Partner Edge",
                    folders=[
                        BrunoFolder(
                            name="Customer",
                            path="Partner Edge/Customer",
                            requests=[
                                _request("Get By Id", "Partner Edge/Customer/Get By Id.bru"),
                            ],
                        ),
                        BrunoFolder(
                            name="Wallet",
                            path="Partner Edge/Wallet",
                            requests=[
                                _request("Get By Id", "Partner Edge/Wallet/Get By Id.bru"),
                            ],
                        ),
                    ],
                )
            ],
        )

        plans = plan_collection_outputs(
            collection,
            default_mode=split_mode.REQUEST_TREE,
            rules=[],
        )

        planned_paths = {Path(plan.relative_output_path) for plan in plans}
        assert planned_paths == {
            Path("partner_edge/customer/get_by_id.robot"),
            Path("partner_edge/wallet/get_by_id.robot"),
        }

    def test_top_folder_planner_preserves_collection_folder_order_for_compatibility(self):
        """Compatibility top-folder planning should keep collection order instead of re-sorting suites."""
        split_mode, layout_rule, plan_collection_outputs = _load_planner_api()

        collection = BrunoCollection(
            name="Paymont",
            requests=[_request("Root Health", "Health Check.bru")],
            folders=[
                BrunoFolder(
                    name="Zeta Area",
                    path="Zeta Area",
                    requests=[_request("Zeta Request", "Zeta Area/Zeta Request.bru")],
                ),
                BrunoFolder(
                    name="Alpha Area",
                    path="Alpha Area",
                    requests=[_request("Alpha Request", "Alpha Area/Alpha Request.bru")],
                ),
            ],
        )

        plans = plan_collection_outputs(
            collection,
            default_mode=split_mode.TOP_FOLDER,
            rules=[],
        )

        assert [Path(plan.relative_output_path) for plan in plans] == [
            Path("zeta_area.robot"),
            Path("alpha_area.robot"),
            Path("paymont.robot"),
        ]

    def test_route_rules_use_first_matching_rule(self):
        """Ordered routing rules should be deterministic and first-match wins."""
        split_mode, layout_rule, plan_collection_outputs = _load_planner_api()

        collection = BrunoCollection(
            name="Paymont",
            folders=[
                BrunoFolder(
                    name="Scenario Batch",
                    path="Scenario Batch",
                    folders=[
                        BrunoFolder(
                            name="Client Flow",
                            path="Scenario Batch/Client Flow",
                            requests=[
                                _request(
                                    "Create Client",
                                    "Scenario Batch/Client Flow/01 Create Client.bru",
                                    seq=1,
                                ),
                            ],
                        )
                    ],
                )
            ],
        )

        plans = plan_collection_outputs(
            collection,
            default_mode=split_mode.REQUEST_TREE,
            rules=[
                layout_rule(path_prefix="Scenario Batch", mode=split_mode.FLOW_FOLDER),
                layout_rule(path_prefix="Scenario Batch/Client Flow", mode=split_mode.REQUEST_TREE),
            ],
        )

        assert [Path(plan.relative_output_path) for plan in plans] == [
            Path("scenario_batch/client_flow.robot"),
        ]
        assert plans[0].mode == split_mode.FLOW_FOLDER

    def test_glob_route_rule_matches_nested_folder_paths(self):
        """Wildcard route rules should match arbitrary nested folder names."""
        split_mode, layout_rule, plan_collection_outputs = _load_planner_api()

        collection = BrunoCollection(
            name="Paymont",
            folders=[
                BrunoFolder(
                    name="Flows",
                    path="Flows",
                    folders=[
                        BrunoFolder(
                            name="Client API Flow",
                            path="Flows/Client API Flow",
                            requests=[
                                _request(
                                    "Get Token",
                                    "Flows/Client API Flow/Get Token.bru",
                                    seq=1,
                                ),
                                _request(
                                    "List Customers",
                                    "Flows/Client API Flow/List Customers.bru",
                                    seq=2,
                                ),
                            ],
                        )
                    ],
                )
            ],
        )

        plans = plan_collection_outputs(
            collection,
            default_mode=split_mode.REQUEST_TREE,
            rules=[layout_rule(path_prefix="Flows/*", mode=split_mode.FLOW_FOLDER)],
        )

        assert [Path(plan.relative_output_path) for plan in plans] == [
            Path("flows/client_api_flow.robot"),
        ]
        assert plans[0].mode == split_mode.FLOW_FOLDER
        assert plans[0].preserve_test_order is True

    def test_route_rules_match_case_insensitively(self):
        """Route matching should be case-insensitive for cross-platform consistency."""
        split_mode, layout_rule, plan_collection_outputs = _load_planner_api()

        collection = BrunoCollection(
            name="Paymont",
            folders=[
                BrunoFolder(
                    name="Flows",
                    path="Flows",
                    folders=[
                        BrunoFolder(
                            name="Client API Flow",
                            path="Flows/Client API Flow",
                            requests=[
                                _request(
                                    "Get Token",
                                    "Flows/Client API Flow/Get Token.bru",
                                    seq=1,
                                ),
                            ],
                        )
                    ],
                )
            ],
        )

        plans = plan_collection_outputs(
            collection,
            default_mode=split_mode.REQUEST_TREE,
            rules=[layout_rule(path_prefix="flows/*", mode=split_mode.FLOW_FOLDER)],
        )

        assert [Path(plan.relative_output_path) for plan in plans] == [
            Path("flows/client_api_flow.robot"),
        ]
        assert plans[0].mode == split_mode.FLOW_FOLDER

    def test_request_tree_slug_collisions_get_deterministic_hash_suffix(self):
        """Slug collisions inside one folder should stay unique and deterministic."""
        split_mode, layout_rule, plan_collection_outputs = _load_planner_api()

        collection = BrunoCollection(
            name="Paymont",
            folders=[
                BrunoFolder(
                    name="Shared",
                    path="Shared",
                    requests=[
                        _request("Get User", "Shared/Get User.bru"),
                        _request("Get-User", "Shared/Get-User.bru"),
                        _request("Get.User", "Shared/Get.User.bru"),
                        _request("get_user", "Shared/get_user.bru"),
                    ],
                )
            ],
        )

        plans = plan_collection_outputs(
            collection,
            default_mode=split_mode.REQUEST_TREE,
            rules=[],
        )

        paths = [Path(plan.relative_output_path).as_posix() for plan in plans]
        assert len(paths) == len(set(paths))
        assert "shared/get_user.robot" in paths
        hashed_paths = [path for path in paths if path.startswith("shared/get_user_")]
        assert len(hashed_paths) == 3
        assert all(path.endswith(".robot") for path in hashed_paths)
