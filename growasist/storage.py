"""Crash-resistant standalone persistence for cultivation state and journals."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any

from custom_components.hydroponic_system.const import (
    DEFAULT_DOSING_POLICY,
    DEFAULT_PROFILES,
)
from custom_components.hydroponic_system.grow_profile import (
    DEFAULT_ASSISTANT_SETTINGS,
    DEFAULT_SYSTEM_PROFILE,
    normalize_assistant_settings,
    normalize_system_profile,
)
from custom_components.hydroponic_system.journal import (
    JOURNAL_SCHEMA_VERSION,
    active_cultivation,
    empty_cultivations,
    journal_checksum,
    merge_journal_recovery,
    migrate_journal,
    utc_now,
)
from custom_components.hydroponic_system.plant_catalog import (
    default_plant_catalog,
    normalize_plant_catalog,
)


DATABASE_SCHEMA_VERSION = 1


class StorageError(RuntimeError):
    """Base error for standalone persistence failures."""


class JournalConflictError(StorageError):
    """Raised when an immutable event ID is reused with different content."""


class ImportChecksumError(StorageError):
    """Raised when an imported journal does not match its checksum."""


def default_state() -> dict[str, Any]:
    """Return a complete initial state without an active cultivation."""
    return {
        "schema_version": JOURNAL_SCHEMA_VERSION,
        "active_stage": None,
        "engine_enabled": False,
        "profiles": deepcopy(DEFAULT_PROFILES),
        "system_profile": deepcopy(DEFAULT_SYSTEM_PROFILE),
        "assistant_settings": deepcopy(DEFAULT_ASSISTANT_SETTINGS),
        "plant_catalog": default_plant_catalog(),
        "cultivations": empty_cultivations(),
        "events": [],
        "hardware": {
            "i2c_bus": 1,
            "poll_interval": 30,
            "dosing_policy": deepcopy(DEFAULT_DOSING_POLICY),
            "device_assignments": [],
            "dosing_fluids": [
                {"id": "ph_up", "name": "pH+", "required": True},
                {"id": "ph_down", "name": "pH−", "required": True},
            ],
        },
        "device_registry": {
            "schema_version": 2,
            "devices": {},
            "candidates": {},
            "assignments": {},
            "last_scan": None,
        },
    }


def _json_text(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class GrowAsistStore:
    """SQLite state store with immutable revisions and journal events."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()

    def initialize(self) -> None:
        """Create the database and seed it without replacing an existing state."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            self._create_schema(connection)
            exists = connection.execute(
                "SELECT 1 FROM current_state WHERE singleton = 1"
            ).fetchone()
        if exists is None:
            self.save_state(default_state())

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=5,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            INSERT INTO schema_metadata(key, value)
                VALUES ('database_schema_version', '1')
                ON CONFLICT(key) DO NOTHING;

            CREATE TABLE IF NOT EXISTS state_revisions (
                revision INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                checksum TEXT NOT NULL,
                payload TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS current_state (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                revision INTEGER NOT NULL REFERENCES state_revisions(revision),
                updated_at TEXT NOT NULL,
                checksum TEXT NOT NULL,
                payload TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS journal_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                cultivation_id TEXT,
                created_at TEXT NOT NULL,
                checksum TEXT NOT NULL,
                payload TEXT NOT NULL
            );

            CREATE TRIGGER IF NOT EXISTS journal_events_no_update
            BEFORE UPDATE ON journal_events
            BEGIN
                SELECT RAISE(ABORT, 'journal events are immutable');
            END;

            CREATE TRIGGER IF NOT EXISTS journal_events_no_delete
            BEFORE DELETE ON journal_events
            BEGIN
                SELECT RAISE(ABORT, 'journal events are immutable');
            END;

            CREATE TRIGGER IF NOT EXISTS state_revisions_no_update
            BEFORE UPDATE ON state_revisions
            BEGIN
                SELECT RAISE(ABORT, 'state revisions are immutable');
            END;

            CREATE TRIGGER IF NOT EXISTS state_revisions_no_delete
            BEFORE DELETE ON state_revisions
            BEGIN
                SELECT RAISE(ABORT, 'state revisions are immutable');
            END;
            """
        )

    @staticmethod
    def _decode_checked(payload: str, expected_checksum: str) -> dict[str, Any]:
        value = json.loads(payload)
        if not isinstance(value, dict) or journal_checksum(value) != expected_checksum:
            raise StorageError("Stored state checksum mismatch")
        return value

    def _load_state_from_connection(
        self, connection: sqlite3.Connection
    ) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT payload, checksum FROM current_state WHERE singleton = 1"
        ).fetchone()
        if row is None:
            return None
        try:
            return self._decode_checked(row["payload"], row["checksum"])
        except (json.JSONDecodeError, StorageError):
            revisions = connection.execute(
                "SELECT payload, checksum FROM state_revisions ORDER BY revision DESC"
            ).fetchall()
            for revision in revisions:
                try:
                    return self._decode_checked(
                        revision["payload"], revision["checksum"]
                    )
                except (json.JSONDecodeError, StorageError):
                    continue
            raise StorageError("No valid state revision remains")

    def load_state(self) -> dict[str, Any]:
        """Load and verify the latest complete state."""
        self.initialize()
        with self._connect() as connection:
            state = self._load_state_from_connection(connection)
        if state is None:
            raise StorageError("Standalone state was not initialized")
        return state

    @staticmethod
    def _journal_part(state: dict[str, Any]) -> dict[str, Any]:
        journal, _ = migrate_journal(state)
        return journal

    @staticmethod
    def _normalize_state(value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise StorageError("State must be a JSON object")
        result = deepcopy(default_state())
        result.update(deepcopy(value))
        journal, _ = migrate_journal(value)
        result.update(journal)
        result["system_profile"] = normalize_system_profile(
            value.get("system_profile")
        )
        result["assistant_settings"] = normalize_assistant_settings(
            value.get("assistant_settings")
        )
        result["plant_catalog"] = normalize_plant_catalog(
            value.get("plant_catalog")
        )
        # Legacy generic stage profiles used to carry product ids.  Product
        # selection is plant-specific now; keep the old revision recoverable
        # but never let unrelated plants inherit those assignments.
        profiles = result.get("profiles")
        if isinstance(profiles, dict):
            for profile in profiles.values():
                if isinstance(profile, dict):
                    profile.pop("nutrient_ids", None)
        active = active_cultivation(result)
        transitions = active.get("transitions", []) if active else []
        result["active_stage"] = (
            transitions[-1].get("stage") if transitions else None
        )
        # Automatic control cannot be enabled by an import or migration.
        result["engine_enabled"] = False
        return result

    def save_state(self, value: dict[str, Any]) -> dict[str, Any]:
        """Atomically save state while retaining every prior event and revision."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        incoming = self._normalize_state(value)
        with self._connect() as connection:
            self._create_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                current = self._load_state_from_connection(connection)
                if current is not None:
                    merged, _ = merge_journal_recovery(
                        self._journal_part(incoming), self._journal_part(current)
                    )
                    incoming.update(merged)
                    active = active_cultivation(incoming)
                    transitions = active.get("transitions", []) if active else []
                    incoming["active_stage"] = (
                        transitions[-1].get("stage") if transitions else None
                    )

                for event in incoming.get("events", []):
                    event_id = str(event.get("id") or "")
                    if not event_id:
                        raise StorageError("Journal event id is required")
                    event_checksum = journal_checksum(event)
                    existing = connection.execute(
                        "SELECT checksum FROM journal_events WHERE event_id = ?",
                        (event_id,),
                    ).fetchone()
                    if existing is not None:
                        if existing["checksum"] != event_checksum:
                            raise JournalConflictError(
                                f"Journal event {event_id} cannot be changed"
                            )
                        continue
                    connection.execute(
                        """
                        INSERT INTO journal_events(
                            event_id, cultivation_id, created_at, checksum, payload
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            event_id,
                            event.get("cultivation_id"),
                            str(event.get("created_at") or utc_now()),
                            event_checksum,
                            _json_text(event),
                        ),
                    )

                saved_at = utc_now()
                payload = _json_text(incoming)
                checksum = journal_checksum(incoming)
                cursor = connection.execute(
                    """
                    INSERT INTO state_revisions(created_at, checksum, payload)
                    VALUES (?, ?, ?)
                    """,
                    (saved_at, checksum, payload),
                )
                revision = int(cursor.lastrowid)
                connection.execute(
                    """
                    INSERT INTO current_state(
                        singleton, revision, updated_at, checksum, payload
                    ) VALUES (1, ?, ?, ?, ?)
                    ON CONFLICT(singleton) DO UPDATE SET
                        revision = excluded.revision,
                        updated_at = excluded.updated_at,
                        checksum = excluded.checksum,
                        payload = excluded.payload
                    """,
                    (revision, saved_at, checksum, payload),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return deepcopy(incoming)

    def import_home_assistant_export(
        self, export: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge a checksummed HA export without replacing local history."""
        if not isinstance(export, dict):
            raise ImportChecksumError("Import must be a JSON object")
        supplied_checksum = str(export.get("checksum") or "")
        unsigned = deepcopy(export)
        unsigned.pop("checksum", None)
        if not supplied_checksum or journal_checksum(unsigned) != supplied_checksum:
            raise ImportChecksumError("Home Assistant export checksum mismatch")

        state = self.load_state()
        incoming_journal, _ = migrate_journal(export)
        merged, _ = merge_journal_recovery(
            self._journal_part(state), incoming_journal
        )
        state.update(merged)
        if "current_system_profile" in export:
            state["system_profile"] = normalize_system_profile(
                export.get("current_system_profile")
            )
        if "plant_catalog" in export:
            state["plant_catalog"] = normalize_plant_catalog(
                export.get("plant_catalog")
            )
        if isinstance(export.get("profiles"), dict):
            state["profiles"] = deepcopy(export["profiles"])
        if isinstance(export.get("hardware"), dict):
            state["hardware"] = deepcopy(export["hardware"])
        if isinstance(export.get("assistant_settings"), dict):
            state["assistant_settings"] = deepcopy(export["assistant_settings"])
        return self.save_state(state)

    def export_journal(self) -> dict[str, Any]:
        """Return a Home Assistant-compatible, checksummed journal export."""
        state = self.load_state()
        payload = {
            "export_version": 1,
            "schema_version": JOURNAL_SCHEMA_VERSION,
            "generated_at": utc_now(),
            "cultivations": deepcopy(state.get("cultivations", empty_cultivations())),
            "events": deepcopy(state.get("events", [])),
            "current_system_profile": deepcopy(state.get("system_profile", {})),
            "plant_catalog": deepcopy(state.get("plant_catalog", {})),
            "profiles": deepcopy(state.get("profiles", {})),
            "hardware": deepcopy(state.get("hardware", {})),
            "assistant_settings": deepcopy(state.get("assistant_settings", {})),
        }
        return {**payload, "checksum": journal_checksum(payload)}

    def health(self) -> dict[str, Any]:
        """Return storage integrity and durable record counts."""
        self.initialize()
        with self._connect() as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            revision_count = connection.execute(
                "SELECT COUNT(*) FROM state_revisions"
            ).fetchone()[0]
            event_count = connection.execute(
                "SELECT COUNT(*) FROM journal_events"
            ).fetchone()[0]
            state = self._load_state_from_connection(connection)
        active = active_cultivation(state or {})
        return {
            "ok": integrity == "ok" and state is not None,
            "database": str(self.database_path),
            "sqlite_integrity": integrity,
            "journal_schema_version": JOURNAL_SCHEMA_VERSION,
            "database_schema_version": DATABASE_SCHEMA_VERSION,
            "revision_count": int(revision_count),
            "event_count": int(event_count),
            "active_cultivation_id": active.get("id") if active else None,
            "engine_enabled": False,
        }

    def backup(self, destination: str | Path) -> Path:
        """Create a consistent SQLite backup while the service is running."""
        self.initialize()
        target = Path(destination).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(f"{target.suffix}.partial")
        if temporary.exists():
            temporary.unlink()
        with self._connect() as source, sqlite3.connect(temporary) as backup:
            source.backup(backup)
        shutil.move(temporary, target)
        return target
