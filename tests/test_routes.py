"""
Route-level tests: every page loads, both form endpoints behave correctly
on valid and invalid input, and a battery of "hostile input" cases don't
crash the app (SQL special characters, HTML/XSS, oversized input,
malformed IDs, wrong HTTP methods).
"""
import pytest


# ----------------------------------------------------------------------
# Pages load
# ----------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/", "/spots", "/vehicles", "/events", "/analytics"])
def test_page_loads(client, path):
    resp = client.get(path)
    assert resp.status_code == 200


def test_dashboard_has_action_buttons(client):
    resp = client.get("/")
    assert b"New Parking Event" in resp.data
    assert b"Add Vehicle" in resp.data


def test_dashboard_shows_events_table(client):
    resp = client.get("/")
    assert b"dashboard-events-table" in resp.data
    assert b"Recorded parking events" in resp.data
    assert b"XYZ999" in resp.data  # seeded event's vehicle plate should appear
    assert b"col-filter" in resp.data
    assert b"sort-arrow" in resp.data


def test_all_pages_have_nav_links(client):
    for path in ["/", "/spots", "/vehicles", "/events", "/analytics"]:
        resp = client.get(path)
        assert b"Dashboard" in resp.data
        assert b"Analytics" in resp.data


# ----------------------------------------------------------------------
# /create — valid cases (plate-based booking)
# ----------------------------------------------------------------------

def test_create_event_public_spot_any_vehicle_succeeds(client):
    resp = client.post("/create", data={
        "spot_id": "16", "vehicle_lpn": "ABC123",
        "entry_date": "2026-09-05", "entry_time": "09:00", "duration_hours": "2",
    }, follow_redirects=True)
    assert b"created" in resp.data


def test_create_event_private_spot_owners_vehicle_succeeds(client):
    resp = client.post("/create", data={
        "spot_id": "1", "vehicle_lpn": "ABC123",  # spot 1 owned by owner 1, ABC123 owned by owner 1
        "entry_date": "2026-09-05", "entry_time": "09:00", "duration_hours": "2",
    }, follow_redirects=True)
    assert b"created" in resp.data


def test_create_event_plate_lookup_is_case_and_whitespace_insensitive(client):
    resp = client.post("/create", data={
        "spot_id": "16", "vehicle_lpn": "  abc123  ",
        "entry_date": "2026-09-05", "entry_time": "09:00", "duration_hours": "2",
    }, follow_redirects=True)
    assert b"created" in resp.data


# ----------------------------------------------------------------------
# /create — inline vehicle registration for an unregistered plate
# ----------------------------------------------------------------------

def test_create_event_unregistered_plate_registers_and_books(client, app_module):
    resp = client.post("/create", data={
        "spot_id": "16", "vehicle_lpn": "BRANDNEW1",
        "entry_date": "2026-09-05", "entry_time": "09:00", "duration_hours": "2",
        "new_vehicle_make": "Ford", "new_vehicle_model": "Focus", "new_vehicle_color": "Blue",
        "new_owner_choice": "unknown",
    }, follow_redirects=True)
    assert b"registered" in resp.data
    assert b"created" in resp.data
    vehicle = app_module.get_vehicle_by_lpn("BRANDNEW1")
    assert vehicle is not None
    assert vehicle["ownerID"] == app_module.UNKNOWN_OWNER_ID


def test_create_event_unregistered_plate_with_known_owner(client, app_module):
    resp = client.post("/create", data={
        "spot_id": "2", "vehicle_lpn": "BRANDNEW2",  # spot 2 owned by owner 2
        "entry_date": "2026-09-05", "entry_time": "09:00", "duration_hours": "2",
        "new_vehicle_make": "Kia", "new_vehicle_model": "Rio", "new_vehicle_color": "Red",
        "new_owner_choice": "2",
    }, follow_redirects=True)
    assert b"created" in resp.data
    vehicle = app_module.get_vehicle_by_lpn("BRANDNEW2")
    assert vehicle["ownerID"] == 2


def test_create_event_unregistered_plate_wrong_private_owner_rejected(client, app_module):
    resp = client.post("/create", data={
        "spot_id": "1", "vehicle_lpn": "BRANDNEW3",  # spot 1 owned by owner 1
        "entry_date": "2026-09-05", "entry_time": "09:00", "duration_hours": "2",
        "new_owner_choice": "2",  # registering under owner 2 instead
    }, follow_redirects=True)
    assert b"not owned by" in resp.data
    # the vehicle should still have been registered even though the booking failed
    assert app_module.get_vehicle_by_lpn("BRANDNEW3") is not None


# ----------------------------------------------------------------------
# /create — business rule violations
# ----------------------------------------------------------------------

def test_create_event_private_spot_wrong_owner_rejected(client):
    resp = client.post("/create", data={
        "spot_id": "1", "vehicle_lpn": "DEF456",  # spot 1 owned by owner 1, DEF456 owned by owner 2
        "entry_date": "2026-09-05", "entry_time": "09:00", "duration_hours": "2",
    }, follow_redirects=True)
    assert b"not owned by" in resp.data


def test_create_event_overlapping_spot_rejected(client):
    resp = client.post("/create", data={
        "spot_id": "16", "vehicle_lpn": "ABC123",
        "entry_date": "2026-08-20", "entry_time": "10:00", "duration_hours": "1",  # overlaps seeded 09-11 event
    }, follow_redirects=True)
    assert b"already booked" in resp.data


def test_create_event_vehicle_double_booking_rejected(client):
    # XYZ999 (vehicle 3) is already parked in spot 16 from 09:00-11:00 on 2026-08-20 (seed data)
    resp = client.post("/create", data={
        "spot_id": "17", "vehicle_lpn": "XYZ999",
        "entry_date": "2026-08-20", "entry_time": "10:00", "duration_hours": "1",
    }, follow_redirects=True)
    assert b"already parked elsewhere" in resp.data


@pytest.mark.parametrize("duration", ["0", "11", "-1"])
def test_create_event_invalid_duration_rejected(client, duration):
    resp = client.post("/create", data={
        "spot_id": "16", "vehicle_lpn": "ABC123",
        "entry_date": "2026-09-05", "entry_time": "09:00", "duration_hours": duration,
    }, follow_redirects=True)
    assert b"Duration must be between" in resp.data


def test_create_event_nonexistent_spot_rejected(client):
    resp = client.post("/create", data={
        "spot_id": "9999", "vehicle_lpn": "ABC123",
        "entry_date": "2026-09-05", "entry_time": "09:00", "duration_hours": "2",
    }, follow_redirects=True)
    assert b"no longer exists" in resp.data


def test_create_event_missing_plate_rejected(client):
    resp = client.post("/create", data={
        "spot_id": "16", "vehicle_lpn": "",
        "entry_date": "2026-09-05", "entry_time": "09:00", "duration_hours": "2",
    }, follow_redirects=True)
    assert b"License plate is required" in resp.data


# ----------------------------------------------------------------------
# /api/vehicle_by_plate
# ----------------------------------------------------------------------

def test_api_vehicle_by_plate_found(client):
    resp = client.get("/api/vehicle_by_plate", query_string={"lpn": "ABC123"})
    data = resp.get_json()
    assert data["found"] is True
    assert data["vehicle"]["vehicleID"] == 1


def test_api_vehicle_by_plate_case_and_whitespace_insensitive(client):
    resp = client.get("/api/vehicle_by_plate", query_string={"lpn": "  abc123  "})
    data = resp.get_json()
    assert data["found"] is True
    assert data["vehicle"]["vehicleID"] == 1


def test_api_vehicle_by_plate_not_found(client):
    resp = client.get("/api/vehicle_by_plate", query_string={"lpn": "NOSUCHPLATE"})
    data = resp.get_json()
    assert data["found"] is False


def test_api_vehicle_by_plate_missing_param(client):
    resp = client.get("/api/vehicle_by_plate")
    assert resp.status_code == 400


# ----------------------------------------------------------------------
# /api/eligible_spots — owner_id branch (unregistered plate)
# ----------------------------------------------------------------------

def test_api_eligible_spots_by_owner_id_for_unregistered_plate(client):
    resp = client.get("/api/eligible_spots", query_string={
        "owner_id": 1, "entry_date": "2026-09-05", "entry_time": "09:00", "duration_hours": 2,
    })
    data = resp.get_json()
    spot1 = next(s for s in data["spots"] if s["spotID"] == 1)   # owner 1's private spot
    spot2 = next(s for s in data["spots"] if s["spotID"] == 2)   # owner 2's private spot
    assert spot1["eligible"] is True
    assert spot2["eligible"] is False


# ----------------------------------------------------------------------
# /vehicles/add
# ----------------------------------------------------------------------

def test_add_vehicle_unknown_owner_succeeds(client):
    resp = client.post("/vehicles/add", data={
        "vehicle_lpn": "NEWV001", "vehicle_make": "Ford", "vehicle_model": "Focus",
        "vehicle_color": "Blue", "owner_choice": "unknown",
    }, follow_redirects=True)
    assert b"added" in resp.data
    assert b"NEWV001" in client.get("/vehicles").data


def test_add_vehicle_known_owner_succeeds(client):
    resp = client.post("/vehicles/add", data={
        "vehicle_lpn": "NEWV002", "vehicle_make": "Kia", "vehicle_model": "Rio",
        "vehicle_color": "Red", "owner_choice": "2",
    }, follow_redirects=True)
    assert b"added" in resp.data
    assert b"Maria Garcia" in client.get("/vehicles").data


def test_add_vehicle_missing_plate_rejected(client):
    resp = client.post("/vehicles/add", data={
        "vehicle_lpn": "", "vehicle_make": "Ford", "owner_choice": "unknown",
    }, follow_redirects=True)
    assert b"required" in resp.data


def test_add_vehicle_duplicate_plate_rejected_gracefully(client):
    resp = client.post("/vehicles/add", data={
        "vehicle_lpn": "ABC123", "vehicle_make": "Dup", "owner_choice": "unknown",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Could not add" in resp.data


# ----------------------------------------------------------------------
# API endpoints
# ----------------------------------------------------------------------

def test_api_eligible_spots_missing_params(client):
    resp = client.get("/api/eligible_spots")
    assert resp.status_code == 400


def test_api_eligible_spots_invalid_date(client):
    resp = client.get("/api/eligible_spots", query_string={
        "vehicle_id": 1, "entry_date": "not-a-date", "entry_time": "09:00", "duration_hours": 2,
    })
    assert resp.status_code == 400


def test_api_eligible_spots_marks_private_spot_correctly(client):
    resp = client.get("/api/eligible_spots", query_string={
        "vehicle_id": 2, "entry_date": "2026-09-05", "entry_time": "09:00", "duration_hours": 2,
    })
    data = resp.get_json()
    spot1 = next(s for s in data["spots"] if s["spotID"] == 1)
    assert spot1["eligible"] is False  # vehicle 2 not owned by spot 1's owner


def test_api_vehicles_for_spot_private(client):
    resp = client.get("/api/vehicles/1")
    data = resp.get_json()
    assert data["spot_type"] == "private"
    assert [v["vehicleID"] for v in data["vehicles"]] == [1]


def test_api_vehicles_for_nonexistent_spot(client):
    resp = client.get("/api/vehicles/9999")
    assert resp.status_code == 404


def test_api_spot_events_returns_list(client):
    resp = client.get("/api/spot_events/16")
    data = resp.get_json()
    assert len(data["events"]) == 1
    assert data["events"][0]["vehicle_LPN"] == "XYZ999"


# ----------------------------------------------------------------------
# Robustness: hostile / malformed input
# ----------------------------------------------------------------------

def test_create_event_non_numeric_spot_id_handled(client):
    resp = client.post("/create", data={
        "spot_id": "not-a-number", "vehicle_lpn": "ABC123",
        "entry_date": "2026-09-05", "entry_time": "09:00", "duration_hours": "2",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Invalid form submission" in resp.data


def test_create_event_missing_fields_handled(client):
    resp = client.post("/create", data={"spot_id": "1"}, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Invalid form submission" in resp.data


def test_add_vehicle_sql_special_characters_in_plate(client):
    """A plate containing a single quote must not break the (parameterized) query."""
    resp = client.post("/vehicles/add", data={
        "vehicle_lpn": "O'BRIEN-1", "vehicle_make": "Ford", "owner_choice": "unknown",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"added" in resp.data
    assert "O&#39;BRIEN-1".encode() in resp.data or b"O'BRIEN-1" in resp.data


def test_add_vehicle_html_input_is_escaped_not_executed(client):
    """HTML/XSS in a free-text field must render as literal text, not be interpreted as markup."""
    resp = client.post("/vehicles/add", data={
        "vehicle_lpn": "XSSTEST1", "vehicle_make": "<script>alert(1)</script>", "owner_choice": "unknown",
    }, follow_redirects=True)
    assert resp.status_code == 200
    listing = client.get("/vehicles").data
    assert b"<script>alert(1)</script>" not in listing  # not rendered as raw executable markup
    assert b"XSSTEST1" in listing


def test_add_vehicle_oversized_input_does_not_crash(client):
    resp = client.post("/vehicles/add", data={
        "vehicle_lpn": "BIG" + ("X" * 5000), "vehicle_make": "Ford", "owner_choice": "unknown",
    }, follow_redirects=True)
    assert resp.status_code == 200  # either accepted or a clean DB error — never a 500


@pytest.mark.parametrize("path,method", [
    ("/create", "GET"),
    ("/vehicles/add", "GET"),
])
def test_form_endpoints_reject_wrong_http_method(client, path, method):
    resp = client.open(path, method=method)
    assert resp.status_code == 405


def test_api_eligible_spots_non_integer_vehicle_id(client):
    resp = client.get("/api/eligible_spots", query_string={
        "vehicle_id": "not-a-number", "entry_date": "2026-09-05", "entry_time": "09:00", "duration_hours": 2,
    })
    assert resp.status_code == 400
