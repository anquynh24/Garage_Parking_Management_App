"""
Garage Parking Event Creator (Flask)
-------------------------------------
A small Flask web app for creating new PARKING_EVENT records.

Business rules enforced:
  - Public spots can be used by any vehicle.
  - Private spots can ONLY be used by a vehicle owned by that spot's owner.
  - A spot cannot have two overlapping parking events.
  - A vehicle cannot be in two spots at the same time.
  - Duration must be between 1 and 10 hours.

Set your MySQL connection details in the CONFIGURATION section below,
then just run: python app.py

Expected schema:
  GARAGE_SPOT(spotID, spot_floor, spot_number, spot_type, ownerID)
  OWNER(ownerID, owner_first_name, owner_last_name, owner_email)
  VEHICLE(vehicleID, vehicle_LPN, vehicle_make, vehicle_model, vehicle_color, ownerID)
  PARKING_EVENT(eventID, vehicleID, spotID, time_from, time_to)
"""

import os
import sys
from datetime import datetime, timedelta
from urllib.parse import quote_plus

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# ============================================================
# CONFIGURATION — edit these for your remote MySQL server
# (Environment variables of the same name override these if set,
#  so you can leave this block as-is for local dev and set env vars in production.)
# ============================================================
DB_HOST = os.environ.get("DB_HOST", "your-remote-host.com")
DB_PORT = os.environ.get("DB_PORT", "3306")
DB_USER = os.environ.get("DB_USER", "your_username")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "your_password")
DB_NAME = os.environ.get("DB_NAME", "garage")

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

# The OWNER row used to represent "no known owner" for a vehicle.
UNKNOWN_OWNER_ID = 999
# ============================================================

app = Flask(__name__)
app.secret_key = SECRET_KEY


def build_mysql_url(host: str, port: str, user: str, password: str, database: str) -> str:
    """Build a SQLAlchemy MySQL connection string.
    Username/password are URL-encoded so special characters (@, :, /, etc.) don't break the URL.
    """
    user_enc = quote_plus(user)
    pass_enc = quote_plus(password)
    return f"mysql+pymysql://{user_enc}:{pass_enc}@{host}:{port}/{database}"


def redact(conn_str: str) -> str:
    if "@" in conn_str and "://" in conn_str:
        scheme, rest = conn_str.split("://", 1)
        if "@" in rest:
            creds, host_part = rest.rsplit("@", 1)
            user = creds.split(":")[0]
            return f"{scheme}://{user}:***@{host_part}"
    return conn_str


DATABASE_URL = build_mysql_url(DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
engine_label = redact(DATABASE_URL)

try:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
except SQLAlchemyError as e:
    print(f"\nERROR: could not connect to MySQL at {engine_label}\n  {e}\n")
    print("Check the DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME values "
          "in the CONFIGURATION section at the top of app.py (or the matching "
          "environment variables) and try again.\n")
    sys.exit(1)

# ----------------------------------------------------------------------
# Data access helpers
# ----------------------------------------------------------------------

def fetch_spots():
    query = """
        SELECT s.spotID, s.spot_floor, s.spot_number, s.spot_type, s.ownerID,
               o.owner_first_name, o.owner_last_name
        FROM GARAGE_SPOT s
        LEFT JOIN OWNER o ON s.ownerID = o.ownerID
        ORDER BY s.spot_floor, s.spot_number
    """
    with engine.connect() as conn:
        return [dict(row._mapping) for row in conn.execute(text(query))]


def fetch_vehicles(owner_id=None):
    query = """
        SELECT v.vehicleID, v.vehicle_LPN, v.vehicle_make, v.vehicle_model, v.vehicle_color, v.ownerID,
               o.owner_first_name, o.owner_last_name
        FROM VEHICLE v
        LEFT JOIN OWNER o ON v.ownerID = o.ownerID
    """
    params = {}
    if owner_id is not None:
        query += " WHERE v.ownerID = :owner_id"
        params["owner_id"] = owner_id
    query += " ORDER BY v.vehicleID"
    with engine.connect() as conn:
        return [dict(row._mapping) for row in conn.execute(text(query), params)]


def get_vehicle_by_lpn(lpn: str):
    """Case- and whitespace-insensitive plate lookup, used for plate-based booking."""
    query = """
        SELECT v.vehicleID, v.vehicle_LPN, v.vehicle_make, v.vehicle_model, v.vehicle_color, v.ownerID,
               o.owner_first_name, o.owner_last_name
        FROM VEHICLE v
        LEFT JOIN OWNER o ON v.ownerID = o.ownerID
        WHERE UPPER(TRIM(v.vehicle_LPN)) = UPPER(TRIM(:lpn))
    """
    with engine.connect() as conn:
        row = conn.execute(text(query), {"lpn": lpn}).mappings().first()
    return dict(row) if row else None


def fetch_owners_with_private_spots():
    """Owners who currently hold at least one private spot — eligible to be assigned as a vehicle's owner."""
    query = """
        SELECT DISTINCT o.ownerID, o.owner_first_name, o.owner_last_name
        FROM OWNER o
        JOIN GARAGE_SPOT s ON s.ownerID = o.ownerID
        WHERE s.spot_type = 'private'
        ORDER BY o.owner_last_name, o.owner_first_name
    """
    with engine.connect() as conn:
        return [dict(row._mapping) for row in conn.execute(text(query))]


def next_vehicle_id() -> int:
    with engine.connect() as conn:
        max_id = conn.execute(text("SELECT MAX(vehicleID) FROM VEHICLE")).scalar()
    return (max_id or 0) + 1


def insert_vehicle(vehicle_id: int, lpn: str, make: str, model: str, color: str, owner_id):
    query = """
        INSERT INTO VEHICLE (vehicleID, vehicle_LPN, vehicle_make, vehicle_model, vehicle_color, ownerID)
        VALUES (:vehicle_id, :lpn, :make, :model, :color, :owner_id)
    """
    with engine.begin() as conn:
        conn.execute(
            text(query),
            {"vehicle_id": vehicle_id, "lpn": lpn, "make": make, "model": model, "color": color, "owner_id": owner_id},
        )


def fetch_spot_events(spot_id: int):
    """All recorded bookings for a spot, most recent first — used to show times/durations on the map."""
    query = """
        SELECT pe.eventID, v.vehicle_LPN, pe.time_from, pe.time_to
        FROM PARKING_EVENT pe
        JOIN VEHICLE v ON v.vehicleID = pe.vehicleID
        WHERE pe.spotID = :spot_id
        ORDER BY pe.time_from DESC
    """
    with engine.connect() as conn:
        return [dict(row._mapping) for row in conn.execute(text(query), {"spot_id": spot_id})]


def check_spot_overlap(spot_id: int, start: datetime, end: datetime) -> bool:
    query = """
        SELECT COUNT(*) FROM PARKING_EVENT
        WHERE spotID = :spot_id
          AND time_from < :end
          AND (time_to IS NULL OR time_to > :start)
    """
    with engine.connect() as conn:
        count = conn.execute(text(query), {"spot_id": spot_id, "start": start, "end": end}).scalar()
    return count > 0


def check_vehicle_overlap(vehicle_id: int, start: datetime, end: datetime) -> bool:
    query = """
        SELECT COUNT(*) FROM PARKING_EVENT
        WHERE vehicleID = :vehicle_id
          AND time_from < :end
          AND (time_to IS NULL OR time_to > :start)
    """
    with engine.connect() as conn:
        count = conn.execute(text(query), {"vehicle_id": vehicle_id, "start": start, "end": end}).scalar()
    return count > 0


def next_event_id() -> int:
    with engine.connect() as conn:
        max_id = conn.execute(text("SELECT MAX(eventID) FROM PARKING_EVENT")).scalar()
    return (max_id or 0) + 1


def insert_event(event_id: int, vehicle_id: int, spot_id: int, start: datetime, end: datetime):
    query = """
        INSERT INTO PARKING_EVENT (eventID, vehicleID, spotID, time_from, time_to)
        VALUES (:event_id, :vehicle_id, :spot_id, :start, :end)
    """
    with engine.begin() as conn:
        conn.execute(
            text(query),
            {"event_id": event_id, "vehicle_id": vehicle_id, "spot_id": spot_id, "start": start, "end": end},
        )


def fetch_all_events():
    """Every recorded parking event — the start page shows the full history, not just recent ones."""
    query = """
        SELECT pe.eventID, v.vehicle_LPN, v.vehicle_make, v.vehicle_model, s.spotID, s.spot_floor, s.spot_type,
               pe.time_from, pe.time_to
        FROM PARKING_EVENT pe
        JOIN VEHICLE v ON v.vehicleID = pe.vehicleID
        JOIN GARAGE_SPOT s ON s.spotID = pe.spotID
        ORDER BY pe.eventID DESC
    """
    with engine.connect() as conn:
        return [dict(row._mapping) for row in conn.execute(text(query))]


def fetch_owner_spot_counts():
    """Every owner and how many private spots they hold — including owners with zero, excluding the Unknown sentinel."""
    query = """
        SELECT o.ownerID, o.owner_first_name, o.owner_last_name,
               COUNT(s.spotID) AS spot_count
        FROM OWNER o
        LEFT JOIN GARAGE_SPOT s ON s.ownerID = o.ownerID AND s.spot_type = 'private'
        WHERE o.ownerID != :unknown_id
        GROUP BY o.ownerID, o.owner_first_name, o.owner_last_name
        ORDER BY spot_count DESC, o.owner_last_name, o.owner_first_name
    """
    with engine.connect() as conn:
        return [dict(row._mapping) for row in conn.execute(text(query), {"unknown_id": UNKNOWN_OWNER_ID})]


def fetch_spot_usage_minutes():
    """Total minutes each spot has been booked, all-time (completed events only).
    Computed in Python rather than with a DB-specific date function, so it works
    the same way regardless of the SQL backend."""
    query = "SELECT spotID, time_from, time_to FROM PARKING_EVENT WHERE time_to IS NOT NULL"
    with engine.connect() as conn:
        rows = [dict(row._mapping) for row in conn.execute(text(query))]

    usage = {}
    for r in rows:
        start, end = r["time_from"], r["time_to"]
        if isinstance(start, str):
            start = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
        if isinstance(end, str):
            end = datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
        minutes = (end - start).total_seconds() / 60
        usage[r["spotID"]] = usage.get(r["spotID"], 0) + minutes
    return usage


def spot_label(s):
    base = f"Spot {s['spotID']} — Floor {s['spot_floor']}, #{s['spot_number']} ({s['spot_type']})"
    if s["spot_type"] == "private" and s["ownerID"] is not None:
        base += f" — owner: {s['owner_first_name']} {s['owner_last_name']}"
    return base


def vehicle_label(v):
    base = f"{v['vehicle_LPN']} — {v['vehicle_make']} {v['vehicle_model']} ({v['vehicle_color']})"
    if v.get("ownerID") == UNKNOWN_OWNER_ID or not v.get("owner_first_name"):
        base += " — owner: unknown"
    else:
        base += f" — owner: {v['owner_first_name']} {v['owner_last_name']}"
    return base


# ----------------------------------------------------------------------
# Main routes
# ----------------------------------------------------------------------

@app.route("/")
def index():
    try:
        spots = fetch_spots()
        vehicles = fetch_vehicles()
        private_owners = fetch_owners_with_private_spots()
        events = fetch_all_events()
        counts = {
            "spots": len(spots),
            "vehicles": len(vehicles),
            "events": len(events),
        }
    except SQLAlchemyError as e:
        flash(f"Could not read from the database: {e}", "danger")
        return render_template(
            "index.html", spots=[], vehicles=[], private_owners=[], events=[], counts={}, engine_label=engine_label,
            active_page="dashboard", unknown_owner_id=UNKNOWN_OWNER_ID
        )

    for s in spots:
        s["label"] = spot_label(s)
    for v in vehicles:
        v["label"] = vehicle_label(v)

    return render_template(
        "index.html",
        spots=spots,
        vehicles=vehicles,
        private_owners=private_owners,
        events=events,
        counts=counts,
        engine_label=engine_label,
        active_page="dashboard",
        unknown_owner_id=UNKNOWN_OWNER_ID,
    )


@app.route("/spots")
def spots_page():
    try:
        spots = fetch_spots()
    except SQLAlchemyError as e:
        flash(f"Could not read from the database: {e}", "danger")
        spots = []
    return render_template("spots.html", spots=spots, engine_label=engine_label, active_page="spots")


@app.route("/vehicles")
def vehicles_page():
    try:
        vehicles = fetch_vehicles()
        private_owners = fetch_owners_with_private_spots()
    except SQLAlchemyError as e:
        flash(f"Could not read from the database: {e}", "danger")
        vehicles, private_owners = [], []
    for v in vehicles:
        v["label"] = vehicle_label(v)
    return render_template(
        "vehicles.html", vehicles=vehicles, private_owners=private_owners,
        engine_label=engine_label, active_page="vehicles"
    )


@app.route("/events")
def events_page():
    try:
        events = fetch_all_events()
    except SQLAlchemyError as e:
        flash(f"Could not read from the database: {e}", "danger")
        events = []
    return render_template("events.html", events=events, engine_label=engine_label, active_page="events")


@app.route("/analytics")
def analytics_page():
    try:
        spots = fetch_spots()
        usage = fetch_spot_usage_minutes()
        owner_counts = fetch_owner_spot_counts()
    except SQLAlchemyError as e:
        flash(f"Could not read from the database: {e}", "danger")
        return render_template(
            "analytics.html", spot_usage=[], top5=[], max_minutes=1, owner_counts=[], engine_label=engine_label, active_page="analytics"
        )

    spot_usage = []
    for s in spots:
        minutes = round(usage.get(s["spotID"], 0), 1)
        spot_usage.append({**s, "minutes": minutes})
    spot_usage.sort(key=lambda x: x["minutes"], reverse=True)

    top5 = spot_usage[:5]
    max_minutes = max((s["minutes"] for s in top5), default=0) or 1

    return render_template(
        "analytics.html",
        spot_usage=spot_usage,
        top5=top5,
        max_minutes=max_minutes,
        owner_counts=owner_counts,
        engine_label=engine_label,
        active_page="analytics",
    )


@app.route("/api/vehicles/<int:spot_id>")
def api_vehicles_for_spot(spot_id):
    """Return the vehicles eligible for a given spot, as JSON, for the dynamic dropdown."""
    try:
        spots = {s["spotID"]: s for s in fetch_spots()}
    except SQLAlchemyError as e:
        return jsonify({"error": str(e)}), 500

    spot = spots.get(spot_id)
    if spot is None:
        return jsonify({"error": "Spot not found"}), 404

    if spot["spot_type"] == "private":
        vehicles = fetch_vehicles(owner_id=spot["ownerID"])
    else:
        vehicles = fetch_vehicles()

    for v in vehicles:
        v["label"] = vehicle_label(v)

    return jsonify({
        "spot_type": spot["spot_type"],
        "vehicles": vehicles,
    })


@app.route("/api/eligible_spots")
def api_eligible_spots():
    """Given a time window and either a registered vehicle or a chosen owner
    (for a plate that isn't registered yet), return every spot with an eligible/not flag."""
    vehicle_id = request.args.get("vehicle_id", type=int)
    owner_id = request.args.get("owner_id", type=int)
    entry_date = request.args.get("entry_date", "")
    entry_time = request.args.get("entry_time", "")
    duration_hours = request.args.get("duration_hours", type=int)

    if (vehicle_id is None and owner_id is None) or not all([entry_date, entry_time, duration_hours]):
        return jsonify({"error": "missing parameters"}), 400

    try:
        start_dt = datetime.strptime(f"{entry_date} {entry_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        return jsonify({"error": "invalid date/time"}), 400
    end_dt = start_dt + timedelta(hours=duration_hours)

    try:
        spots = fetch_spots()
    except SQLAlchemyError as e:
        return jsonify({"error": str(e)}), 500

    results = []
    for s in spots:
        eligible = True
        reason = ""

        if s["spot_type"] == "private":
            if vehicle_id is not None:
                owned_ids = {v["vehicleID"] for v in fetch_vehicles(owner_id=s["ownerID"])}
                if vehicle_id not in owned_ids:
                    eligible = False
                    reason = "Private spot — not owned by this vehicle's owner"
            elif owner_id != s["ownerID"]:
                eligible = False
                reason = "Private spot — not owned by the selected owner"

        if eligible and check_spot_overlap(s["spotID"], start_dt, end_dt):
            eligible = False
            reason = "Already booked during that time window"

        results.append({
            "spotID": s["spotID"],
            "spot_floor": s["spot_floor"],
            "spot_number": s["spot_number"],
            "spot_type": s["spot_type"],
            "eligible": eligible,
            "reason": reason,
        })

    return jsonify({"spots": results})


@app.route("/api/vehicle_by_plate")
def api_vehicle_by_plate():
    """Look up a vehicle by license plate — drives the inline registration flow."""
    lpn = request.args.get("lpn", "").strip()
    if not lpn:
        return jsonify({"error": "missing lpn"}), 400

    try:
        vehicle = get_vehicle_by_lpn(lpn)
    except SQLAlchemyError as e:
        return jsonify({"error": str(e)}), 500

    if vehicle is None:
        return jsonify({"found": False})

    return jsonify({"found": True, "vehicle": {**vehicle, "label": vehicle_label(vehicle)}})


@app.route("/api/spot_events/<int:spot_id>")
def api_spot_events(spot_id):
    """All recorded bookings for a spot — shown when a spot is clicked on the map,
    so the user can see the times/durations already booked there."""
    try:
        events = fetch_spot_events(spot_id)
    except SQLAlchemyError as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"events": events})


@app.route("/vehicles/add", methods=["POST"])
def add_vehicle():
    lpn = request.form.get("vehicle_lpn", "").strip()
    make = request.form.get("vehicle_make", "").strip()
    model = request.form.get("vehicle_model", "").strip()
    color = request.form.get("vehicle_color", "").strip()
    owner_choice = request.form.get("owner_choice", "unknown")

    if not lpn:
        flash("License plate is required.", "danger")
        return redirect(url_for("index"))

    owner_id = UNKNOWN_OWNER_ID
    if owner_choice != "unknown":
        try:
            owner_id = int(owner_choice)
        except ValueError:
            flash("Invalid owner selection.", "danger")
            return redirect(url_for("index"))

    try:
        new_id = next_vehicle_id()
        insert_vehicle(new_id, lpn, make, model, color, owner_id)
        flash(f"Vehicle #{new_id} ({lpn}) added.", "success")
    except SQLAlchemyError as e:
        flash(f"Could not add the vehicle (plate may already be registered): {e}", "danger")

    return redirect(url_for("index"))


@app.route("/create", methods=["POST"])
def create_event():
    try:
        spot_id = int(request.form["spot_id"])
        lpn = request.form["vehicle_lpn"].strip()
        entry_date = request.form["entry_date"]
        entry_time = request.form["entry_time"]
        duration_hours = int(request.form["duration_hours"])
    except (KeyError, ValueError):
        flash("Invalid form submission.", "danger")
        return redirect(url_for("index"))

    if not lpn:
        flash("License plate is required.", "danger")
        return redirect(url_for("index"))

    if not (1 <= duration_hours <= 10):
        flash("Duration must be between 1 and 10 hours.", "danger")
        return redirect(url_for("index"))

    try:
        start_dt = datetime.strptime(f"{entry_date} {entry_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        flash("Invalid date or time.", "danger")
        return redirect(url_for("index"))

    end_dt = start_dt + timedelta(hours=duration_hours)

    try:
        vehicle = get_vehicle_by_lpn(lpn)

        if vehicle is None:
            # Plate isn't registered yet — register it inline using the details
            # submitted alongside the booking, then continue with the booking.
            owner_choice = request.form.get("new_owner_choice", "unknown")
            owner_id = UNKNOWN_OWNER_ID
            if owner_choice != "unknown":
                try:
                    owner_id = int(owner_choice)
                except ValueError:
                    flash("Invalid owner selection.", "danger")
                    return redirect(url_for("index"))

            make = request.form.get("new_vehicle_make", "").strip()
            model = request.form.get("new_vehicle_model", "").strip()
            color = request.form.get("new_vehicle_color", "").strip()

            new_vehicle_id = next_vehicle_id()
            insert_vehicle(new_vehicle_id, lpn, make, model, color, owner_id)
            vehicle = {"vehicleID": new_vehicle_id, "ownerID": owner_id}
            flash(f"Vehicle #{new_vehicle_id} ({lpn}) registered.", "success")

        vehicle_id = vehicle["vehicleID"]

        spots = {s["spotID"]: s for s in fetch_spots()}
        spot = spots.get(spot_id)
        if spot is None:
            flash("Selected spot no longer exists.", "danger")
            return redirect(url_for("index"))

        if spot["spot_type"] == "private" and vehicle["ownerID"] != spot["ownerID"]:
            flash("That vehicle is not owned by this private spot's owner.", "danger")
            return redirect(url_for("index"))

        if check_spot_overlap(spot_id, start_dt, end_dt):
            flash("This spot is already booked during part of that time window.", "danger")
            return redirect(url_for("index"))

        if check_vehicle_overlap(vehicle_id, start_dt, end_dt):
            flash("This vehicle is already parked elsewhere during part of that time window.", "danger")
            return redirect(url_for("index"))

        new_id = next_event_id()
        insert_event(new_id, vehicle_id, spot_id, start_dt, end_dt)
        flash(
            f"Parking event #{new_id} created: spot {spot_id} booked from "
            f"{start_dt.strftime('%Y-%m-%d %H:%M')} to {end_dt.strftime('%Y-%m-%d %H:%M')}.",
            "success",
        )
    except SQLAlchemyError as e:
        flash(f"Could not create the event: {e}", "danger")

    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
