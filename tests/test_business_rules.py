"""
Unit tests for the data-access / business-rule functions in app.py.
These call the functions directly (no HTTP layer) against the seeded
SQLite test database from conftest.py.
"""
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError


# ----------------------------------------------------------------------
# fetch_spots / fetch_vehicles / labels
# ----------------------------------------------------------------------

def test_fetch_spots_returns_all_with_owner_names(app_module):
    spots = app_module.fetch_spots()
    assert len(spots) == 5
    spot1 = next(s for s in spots if s["spotID"] == 1)
    assert spot1["spot_type"] == "private"
    assert spot1["owner_first_name"] == "James"


def test_fetch_vehicles_filtered_by_owner(app_module):
    vehicles = app_module.fetch_vehicles(owner_id=1)
    assert [v["vehicleID"] for v in vehicles] == [1]


def test_fetch_vehicles_no_filter_returns_all(app_module):
    vehicles = app_module.fetch_vehicles()
    assert len(vehicles) == 3


def test_spot_label_private_shows_owner(app_module):
    spot = next(s for s in app_module.fetch_spots() if s["spotID"] == 1)
    label = app_module.spot_label(spot)
    assert "private" in label and "James Smith" in label


def test_spot_label_public_no_owner(app_module):
    spot = next(s for s in app_module.fetch_spots() if s["spotID"] == 16)
    label = app_module.spot_label(spot)
    assert "public" in label and "owner" not in label


def test_vehicle_label_known_owner(app_module):
    vehicle = app_module.fetch_vehicles(owner_id=1)[0]
    label = app_module.vehicle_label(vehicle)
    assert "owner: James Smith" in label


def test_vehicle_label_unknown_owner_shows_unknown(app_module):
    vehicle = next(v for v in app_module.fetch_vehicles() if v["vehicleID"] == 3)
    label = app_module.vehicle_label(vehicle)
    assert "owner: unknown" in label


# ----------------------------------------------------------------------
# Overlap boundary matrix — the core business rule
# ----------------------------------------------------------------------
# Existing seeded event on spot 16: 2026-08-20 09:00 -> 11:00

OVERLAP_CASES = [
    pytest.param("2026-08-20 07:00", "2026-08-20 09:00", False, id="touches_before_no_overlap"),
    pytest.param("2026-08-20 11:00", "2026-08-20 13:00", False, id="touches_after_no_overlap"),
    pytest.param("2026-08-20 08:00", "2026-08-20 09:30", True, id="partial_overlap_start"),
    pytest.param("2026-08-20 10:30", "2026-08-20 12:00", True, id="partial_overlap_end"),
    pytest.param("2026-08-20 09:30", "2026-08-20 10:30", True, id="fully_inside_existing"),
    pytest.param("2026-08-20 08:00", "2026-08-20 12:00", True, id="fully_contains_existing"),
    pytest.param("2026-08-20 09:00", "2026-08-20 11:00", True, id="identical_range"),
    pytest.param("2026-08-19 09:00", "2026-08-19 11:00", False, id="different_day_no_overlap"),
]


@pytest.mark.parametrize("start_str,end_str,expected", OVERLAP_CASES)
def test_check_spot_overlap(app_module, start_str, end_str, expected):
    start = datetime.strptime(start_str, "%Y-%m-%d %H:%M")
    end = datetime.strptime(end_str, "%Y-%m-%d %H:%M")
    assert app_module.check_spot_overlap(16, start, end) is expected


@pytest.mark.parametrize("start_str,end_str,expected", OVERLAP_CASES)
def test_check_vehicle_overlap(app_module, start_str, end_str, expected):
    start = datetime.strptime(start_str, "%Y-%m-%d %H:%M")
    end = datetime.strptime(end_str, "%Y-%m-%d %H:%M")
    assert app_module.check_vehicle_overlap(3, start, end) is expected


# ----------------------------------------------------------------------
# ID assignment — regression coverage for the "no AUTO_INCREMENT" schema
# ----------------------------------------------------------------------

def test_next_event_id_increments_from_max(app_module):
    assert app_module.next_event_id() == 2  # seed has eventID 1


def test_next_vehicle_id_increments_from_max(app_module):
    assert app_module.next_vehicle_id() == 4  # seed has vehicleIDs 1-3


def test_insert_event_uses_explicit_id(app_module):
    new_id = app_module.next_event_id()
    start = datetime(2026, 9, 1, 9, 0)
    end = datetime(2026, 9, 1, 10, 0)
    app_module.insert_event(new_id, vehicle_id=1, spot_id=1, start=start, end=end)
    events = app_module.fetch_all_events()
    assert any(e["eventID"] == new_id for e in events)


def test_insert_vehicle_uses_explicit_id(app_module):
    new_id = app_module.next_vehicle_id()
    app_module.insert_vehicle(new_id, "NEWPLATE1", "Kia", "Rio", "Red", app_module.UNKNOWN_OWNER_ID)
    vehicles = app_module.fetch_vehicles()
    assert any(v["vehicleID"] == new_id and v["vehicle_LPN"] == "NEWPLATE1" for v in vehicles)


# ----------------------------------------------------------------------
# Vehicle ownership rules
# ----------------------------------------------------------------------

def test_insert_vehicle_with_unknown_owner(app_module):
    new_id = app_module.next_vehicle_id()
    app_module.insert_vehicle(new_id, "UNK000", "Ford", "Focus", "Blue", app_module.UNKNOWN_OWNER_ID)
    vehicle = next(v for v in app_module.fetch_vehicles() if v["vehicleID"] == new_id)
    assert vehicle["ownerID"] == app_module.UNKNOWN_OWNER_ID


def test_insert_vehicle_with_known_owner(app_module):
    new_id = app_module.next_vehicle_id()
    app_module.insert_vehicle(new_id, "KNOWN001", "Tesla", "Model 3", "Black", 2)
    vehicle = next(v for v in app_module.fetch_vehicles() if v["vehicleID"] == new_id)
    assert vehicle["ownerID"] == 2


def test_insert_vehicle_duplicate_plate_raises(app_module):
    new_id = app_module.next_vehicle_id()
    with pytest.raises(IntegrityError):
        app_module.insert_vehicle(new_id, "ABC123", "Dup", "Test", "Grey", app_module.UNKNOWN_OWNER_ID)


# ----------------------------------------------------------------------
# Owner-related queries
# ----------------------------------------------------------------------

def test_fetch_owners_with_private_spots_excludes_unknown(app_module):
    owners = app_module.fetch_owners_with_private_spots()
    owner_ids = {o["ownerID"] for o in owners}
    assert owner_ids == {1, 2}
    assert app_module.UNKNOWN_OWNER_ID not in owner_ids


def test_fetch_owner_spot_counts_includes_zero_and_excludes_unknown(app_module):
    counts = {o["ownerID"]: o["spot_count"] for o in app_module.fetch_owner_spot_counts()}
    assert counts[1] == 2  # owner 1 has spots 1 and 3
    assert counts[2] == 1  # owner 2 has spot 2
    assert app_module.UNKNOWN_OWNER_ID not in counts


# ----------------------------------------------------------------------
# Analytics: usage minutes
# ----------------------------------------------------------------------

def test_fetch_spot_usage_minutes_sums_completed_events_only(app_module):
    usage = app_module.fetch_spot_usage_minutes()
    assert usage[16] == 120.0  # seed event: 09:00 -> 11:00 = 120 minutes


def test_fetch_spot_usage_minutes_ignores_open_ended_events(app_module):
    # An event with no time_to (still parked) should not contribute minutes.
    new_id = app_module.next_event_id()
    with app_module.engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(
            text("INSERT INTO PARKING_EVENT (eventID, vehicleID, spotID, time_from, time_to) "
                 "VALUES (:id, 1, 1, :start, NULL)"),
            {"id": new_id, "start": "2026-09-01 09:00:00"},
        )
    usage = app_module.fetch_spot_usage_minutes()
    assert usage.get(1, 0) == 0


def test_fetch_spot_usage_minutes_zero_for_unused_spot(app_module):
    usage = app_module.fetch_spot_usage_minutes()
    assert usage.get(17, 0) == 0


# ----------------------------------------------------------------------
# Connection string helpers
# ----------------------------------------------------------------------

def test_build_mysql_url_encodes_special_characters(app_module):
    url = app_module.build_mysql_url("host.example.com", "3306", "admin", "p@ss:w/ord", "garage")
    assert url == "mysql+pymysql://admin:p%40ss%3Aw%2Ford@host.example.com:3306/garage"


def test_redact_hides_password(app_module):
    url = "mysql+pymysql://admin:secretpw@host.example.com:3306/garage"
    redacted = app_module.redact(url)
    assert "secretpw" not in redacted
    assert "admin" in redacted and "***" in redacted
