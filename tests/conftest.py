"""
Shared pytest fixtures for the Garage Parking test suite.

The app is written against a remote MySQL server, but the tests never touch
it. Before app.py is imported, this file patches sqlalchemy.create_engine so
that ANY connection string app.py builds (even a real mysql+pymysql:// one)
is silently redirected to a throwaway local SQLite file instead. That file is
recreated with a known schema and seed data before every single test, so
tests are fast, offline, and fully isolated from each other.
"""
import os
import sys
import sqlite3
import tempfile
import pathlib

import pytest

# ----------------------------------------------------------------------
# 1. Make sure app.py's module-level connection check can succeed even
#    with placeholder config — it will actually hit SQLite, not MySQL.
# ----------------------------------------------------------------------
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test")

import sqlalchemy  # noqa: E402

_real_create_engine = sqlalchemy.create_engine
_fd, TEST_DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)


def _sqlite_redirect_engine(url, **kwargs):
    """Ignore whatever URL app.py built and always hand back a SQLite engine."""
    kwargs.pop("pool_pre_ping", None)
    return _real_create_engine(f"sqlite:///{TEST_DB_PATH}")


sqlalchemy.create_engine = _sqlite_redirect_engine

# ----------------------------------------------------------------------
# 2. Now it's safe to import app.py — its startup connection check will
#    succeed against the (currently empty) SQLite file.
# ----------------------------------------------------------------------
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import app as appmod  # noqa: E402

UNKNOWN_OWNER_ID = appmod.UNKNOWN_OWNER_ID

SCHEMA = """
DROP TABLE IF EXISTS PARKING_EVENT;
DROP TABLE IF EXISTS VEHICLE;
DROP TABLE IF EXISTS GARAGE_SPOT;
DROP TABLE IF EXISTS OWNER;

CREATE TABLE OWNER (
    ownerID INTEGER PRIMARY KEY,
    owner_first_name TEXT,
    owner_last_name TEXT,
    owner_email TEXT
);

CREATE TABLE GARAGE_SPOT (
    spotID INTEGER PRIMARY KEY,
    spot_floor INTEGER,
    spot_number INTEGER,
    spot_type TEXT,
    ownerID INTEGER
);

CREATE TABLE VEHICLE (
    vehicleID INTEGER PRIMARY KEY,
    vehicle_LPN TEXT UNIQUE,
    vehicle_make TEXT,
    vehicle_model TEXT,
    vehicle_color TEXT,
    ownerID INTEGER
);

CREATE TABLE PARKING_EVENT (
    eventID INTEGER PRIMARY KEY,
    vehicleID INTEGER,
    spotID INTEGER,
    time_from TEXT,
    time_to TEXT
);
"""

SEED = f"""
INSERT INTO OWNER VALUES
    (1, 'James', 'Smith', 'james@example.com'),
    (2, 'Maria', 'Garcia', 'maria@example.com'),
    ({UNKNOWN_OWNER_ID}, 'Unknown', 'Unknown', 'unknown@example.com');

INSERT INTO GARAGE_SPOT VALUES
    (1, 1, 1, 'private', 1),
    (2, 1, 2, 'private', 2),
    (3, 1, 3, 'private', 1),
    (16, 2, 6, 'public', NULL),
    (17, 2, 7, 'public', NULL);

INSERT INTO VEHICLE VALUES
    (1, 'ABC123', 'Toyota', 'Corolla', 'White', 1),
    (2, 'DEF456', 'Ford', 'Focus', 'Blue', 2),
    (3, 'XYZ999', 'Honda', 'Civic', 'Black', {UNKNOWN_OWNER_ID});

INSERT INTO PARKING_EVENT VALUES
    (1, 3, 16, '2026-08-20 09:00:00', '2026-08-20 11:00:00');
"""


def reset_db():
    conn = sqlite3.connect(TEST_DB_PATH)
    conn.executescript(SCHEMA)
    conn.executescript(SEED)
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def fresh_db():
    """Reset to known seed data before every test — full isolation, no test order dependence."""
    reset_db()
    yield


@pytest.fixture
def app_module():
    """The imported app.py module, so tests can call its functions directly."""
    return appmod


@pytest.fixture
def client():
    appmod.app.config["TESTING"] = True
    appmod.app.secret_key = "test-secret"
    return appmod.app.test_client()
