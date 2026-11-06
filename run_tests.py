#!/usr/bin/env python3
"""
Pinned test runner for the Garage Parking app.

Runs every test in tests/ in an explicit, hand-maintained order (grouped by
feature below), printing a PASS/FAIL line for each test as it completes,
followed by a summary.

If a test is added, removed, or renamed without updating TEST_ORDER below,
this refuses to run and prints exactly what's out of sync, so the pinned
list can never silently drift out of step with the actual test suite.

Usage:
    python run_tests.py
"""
import sys
import pytest

# ============================================================
# Pinned test order, grouped by feature
# ============================================================
TEST_ORDER = [
    # --- Spots, vehicles, labels ---
    "tests/test_business_rules.py::test_fetch_spots_returns_all_with_owner_names",
    "tests/test_business_rules.py::test_fetch_vehicles_filtered_by_owner",
    "tests/test_business_rules.py::test_fetch_vehicles_no_filter_returns_all",
    "tests/test_business_rules.py::test_spot_label_private_shows_owner",
    "tests/test_business_rules.py::test_spot_label_public_no_owner",
    "tests/test_business_rules.py::test_vehicle_label_known_owner",
    "tests/test_business_rules.py::test_vehicle_label_unknown_owner_shows_unknown",

    # --- Spot overlap boundary matrix ---
    "tests/test_business_rules.py::test_check_spot_overlap[touches_before_no_overlap]",
    "tests/test_business_rules.py::test_check_spot_overlap[touches_after_no_overlap]",
    "tests/test_business_rules.py::test_check_spot_overlap[partial_overlap_start]",
    "tests/test_business_rules.py::test_check_spot_overlap[partial_overlap_end]",
    "tests/test_business_rules.py::test_check_spot_overlap[fully_inside_existing]",
    "tests/test_business_rules.py::test_check_spot_overlap[fully_contains_existing]",
    "tests/test_business_rules.py::test_check_spot_overlap[identical_range]",
    "tests/test_business_rules.py::test_check_spot_overlap[different_day_no_overlap]",

    # --- Vehicle overlap boundary matrix ---
    "tests/test_business_rules.py::test_check_vehicle_overlap[touches_before_no_overlap]",
    "tests/test_business_rules.py::test_check_vehicle_overlap[touches_after_no_overlap]",
    "tests/test_business_rules.py::test_check_vehicle_overlap[partial_overlap_start]",
    "tests/test_business_rules.py::test_check_vehicle_overlap[partial_overlap_end]",
    "tests/test_business_rules.py::test_check_vehicle_overlap[fully_inside_existing]",
    "tests/test_business_rules.py::test_check_vehicle_overlap[fully_contains_existing]",
    "tests/test_business_rules.py::test_check_vehicle_overlap[identical_range]",
    "tests/test_business_rules.py::test_check_vehicle_overlap[different_day_no_overlap]",

    # --- ID assignment (no AUTO_INCREMENT in the schema) ---
    "tests/test_business_rules.py::test_next_event_id_increments_from_max",
    "tests/test_business_rules.py::test_next_vehicle_id_increments_from_max",
    "tests/test_business_rules.py::test_insert_event_uses_explicit_id",
    "tests/test_business_rules.py::test_insert_vehicle_uses_explicit_id",

    # --- Vehicle ownership rules ---
    "tests/test_business_rules.py::test_insert_vehicle_with_unknown_owner",
    "tests/test_business_rules.py::test_insert_vehicle_with_known_owner",
    "tests/test_business_rules.py::test_insert_vehicle_duplicate_plate_raises",

    # --- Owner queries ---
    "tests/test_business_rules.py::test_fetch_owners_with_private_spots_excludes_unknown",
    "tests/test_business_rules.py::test_fetch_owner_spot_counts_includes_zero_and_excludes_unknown",

    # --- Analytics: usage minutes ---
    "tests/test_business_rules.py::test_fetch_spot_usage_minutes_sums_completed_events_only",
    "tests/test_business_rules.py::test_fetch_spot_usage_minutes_ignores_open_ended_events",
    "tests/test_business_rules.py::test_fetch_spot_usage_minutes_zero_for_unused_spot",

    # --- Connection string helpers ---
    "tests/test_business_rules.py::test_build_mysql_url_encodes_special_characters",
    "tests/test_business_rules.py::test_redact_hides_password",

    # --- Pages load ---
    "tests/test_routes.py::test_page_loads[/]",
    "tests/test_routes.py::test_page_loads[/spots]",
    "tests/test_routes.py::test_page_loads[/vehicles]",
    "tests/test_routes.py::test_page_loads[/events]",
    "tests/test_routes.py::test_page_loads[/analytics]",
    "tests/test_routes.py::test_dashboard_has_action_buttons",
    "tests/test_routes.py::test_dashboard_shows_events_table",
    "tests/test_routes.py::test_all_pages_have_nav_links",

    # --- /create: valid cases (plate-based booking) ---
    "tests/test_routes.py::test_create_event_public_spot_any_vehicle_succeeds",
    "tests/test_routes.py::test_create_event_private_spot_owners_vehicle_succeeds",
    "tests/test_routes.py::test_create_event_plate_lookup_is_case_and_whitespace_insensitive",

    # --- /create: inline vehicle registration for an unregistered plate ---
    "tests/test_routes.py::test_create_event_unregistered_plate_registers_and_books",
    "tests/test_routes.py::test_create_event_unregistered_plate_with_known_owner",
    "tests/test_routes.py::test_create_event_unregistered_plate_wrong_private_owner_rejected",

    # --- /create: business rule violations ---
    "tests/test_routes.py::test_create_event_private_spot_wrong_owner_rejected",
    "tests/test_routes.py::test_create_event_overlapping_spot_rejected",
    "tests/test_routes.py::test_create_event_vehicle_double_booking_rejected",
    "tests/test_routes.py::test_create_event_invalid_duration_rejected[0]",
    "tests/test_routes.py::test_create_event_invalid_duration_rejected[11]",
    "tests/test_routes.py::test_create_event_invalid_duration_rejected[-1]",
    "tests/test_routes.py::test_create_event_nonexistent_spot_rejected",
    "tests/test_routes.py::test_create_event_missing_plate_rejected",

    # --- /api/vehicle_by_plate ---
    "tests/test_routes.py::test_api_vehicle_by_plate_found",
    "tests/test_routes.py::test_api_vehicle_by_plate_case_and_whitespace_insensitive",
    "tests/test_routes.py::test_api_vehicle_by_plate_not_found",
    "tests/test_routes.py::test_api_vehicle_by_plate_missing_param",

    # --- /api/eligible_spots: owner_id branch (unregistered plate) ---
    "tests/test_routes.py::test_api_eligible_spots_by_owner_id_for_unregistered_plate",

    # --- /vehicles/add ---
    "tests/test_routes.py::test_add_vehicle_unknown_owner_succeeds",
    "tests/test_routes.py::test_add_vehicle_known_owner_succeeds",
    "tests/test_routes.py::test_add_vehicle_missing_plate_rejected",
    "tests/test_routes.py::test_add_vehicle_duplicate_plate_rejected_gracefully",

    # --- API endpoints ---
    "tests/test_routes.py::test_api_eligible_spots_missing_params",
    "tests/test_routes.py::test_api_eligible_spots_invalid_date",
    "tests/test_routes.py::test_api_eligible_spots_marks_private_spot_correctly",
    "tests/test_routes.py::test_api_vehicles_for_spot_private",
    "tests/test_routes.py::test_api_vehicles_for_nonexistent_spot",
    "tests/test_routes.py::test_api_spot_events_returns_list",

    # --- Robustness: hostile / malformed input ---
    "tests/test_routes.py::test_create_event_non_numeric_spot_id_handled",
    "tests/test_routes.py::test_create_event_missing_fields_handled",
    "tests/test_routes.py::test_add_vehicle_sql_special_characters_in_plate",
    "tests/test_routes.py::test_add_vehicle_html_input_is_escaped_not_executed",
    "tests/test_routes.py::test_add_vehicle_oversized_input_does_not_crash",
    "tests/test_routes.py::test_form_endpoints_reject_wrong_http_method[/create-GET]",
    "tests/test_routes.py::test_form_endpoints_reject_wrong_http_method[/vehicles/add-GET]",
    "tests/test_routes.py::test_api_eligible_spots_non_integer_vehicle_id",
]


class PinnedOrderPlugin:
    """Reorders collected tests to match TEST_ORDER exactly, refusing to run
    if the pinned list and the actual collected tests have drifted apart."""

    def __init__(self, order):
        self.order = order
        self.position = {nodeid: i for i, nodeid in enumerate(order)}
        self.results = []  # (nodeid, outcome) pairs, in run order

    def pytest_collection_modifyitems(self, config, items):
        collected_ids = {item.nodeid for item in items}
        pinned_ids = set(self.order)

        missing_from_pin = collected_ids - pinned_ids   # exists in tests/, not in TEST_ORDER
        missing_from_tests = pinned_ids - collected_ids  # in TEST_ORDER, no longer exists

        if missing_from_pin or missing_from_tests:
            lines = ["\nTEST_ORDER in run_tests.py is out of sync with tests/:\n"]
            if missing_from_pin:
                lines.append("  Collected but NOT in TEST_ORDER (add these):")
                for nodeid in sorted(missing_from_pin):
                    lines.append(f"    + {nodeid}")
            if missing_from_tests:
                lines.append("  In TEST_ORDER but NOT collected (remove or fix these):")
                for nodeid in sorted(missing_from_tests):
                    lines.append(f"    - {nodeid}")
            lines.append("\nUpdate TEST_ORDER in run_tests.py to match, then re-run.\n")
            print("\n".join(lines))
            raise pytest.UsageError("TEST_ORDER is out of sync with the collected tests.")

        items.sort(key=lambda item: self.position[item.nodeid])

    def pytest_runtest_logreport(self, report):
        if report.when != "call":
            return
        outcome = "PASS" if report.outcome == "passed" else report.outcome.upper()
        self.results.append((report.nodeid, outcome))
        print(f"[{outcome}] {report.nodeid}")

    def pytest_sessionfinish(self, session, exitstatus):
        passed = sum(1 for _, o in self.results if o == "PASS")
        failed = sum(1 for _, o in self.results if o == "FAILED")
        skipped = sum(1 for _, o in self.results if o == "SKIPPED")
        total = len(self.results)
        print("\n" + "=" * 60)
        print(f"SUMMARY: {passed}/{total} passed, {failed} failed, {skipped} skipped")
        if failed:
            print("\nFailed tests:")
            for nodeid, outcome in self.results:
                if outcome == "FAILED":
                    print(f"  - {nodeid}")
        print("=" * 60)


def main():
    plugin = PinnedOrderPlugin(TEST_ORDER)
    exit_code = pytest.main(["-q", "--no-header"], plugins=[plugin])
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
