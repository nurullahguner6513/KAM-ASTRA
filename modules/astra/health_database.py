"""
ASTRA sağlık veritabanı (SQLite, yalnızca standart kütüphane).

- KAM'ın kendi verilerinden bağımsız ayrı bir dosya kullanır (modules/astra/data/astra.db).
- Zaman damgaları UTC olarak saklanır (YYYY-MM-DDTHH:MM:SSZ).
- Bozuk girişler reddedilir ve rejected_inputs tablosuna yazılır.
- Aynı ölçüm iki kez gelirse tek kayıt tutulur (UNIQUE kısıtları).
- Her satır kaynak türünü taşır; SIMULATED veriler sorgularda ayrıştırılabilir.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from . import get_astra_logger
from .models import SOURCE_TYPES, InvalidDataError, to_utc_iso, utc_now

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "astra.db"
SCHEMA_VERSION = 2

_SOURCE_CHECK = "CHECK(source_type IN ({}))".format(", ".join(f"'{s}'" for s in SOURCE_TYPES))
_COMMON = f"""
    received_at_utc TEXT NOT NULL,
    source_device   TEXT NOT NULL,
    source_type     TEXT NOT NULL {_SOURCE_CHECK},
    quality         REAL NOT NULL CHECK(quality BETWEEN 0 AND 1),
    sync_state      TEXT NOT NULL DEFAULT 'pending'
"""

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS astronauts (
    id             INTEGER PRIMARY KEY,
    name           TEXT NOT NULL UNIQUE,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mission_records (
    id                   INTEGER PRIMARY KEY,
    name                 TEXT NOT NULL UNIQUE,
    start_utc            TEXT NOT NULL,
    end_utc              TEXT,
    local_utc_offset_min INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS health_measurements (
    id              INTEGER PRIMARY KEY,
    astronaut_id    INTEGER NOT NULL REFERENCES astronauts(id),
    metric          TEXT NOT NULL,
    value           REAL NOT NULL,
    unit            TEXT NOT NULL,
    measured_at_utc TEXT NOT NULL,
    status          TEXT NOT NULL CHECK(status IN ('ok', 'suspect')),
    note            TEXT NOT NULL DEFAULT '',
    {_COMMON},
    UNIQUE(astronaut_id, metric, measured_at_utc, source_device)
);
CREATE INDEX IF NOT EXISTS idx_measurements_lookup
    ON health_measurements(astronaut_id, metric, measured_at_utc);
CREATE TABLE IF NOT EXISTS sleep_records (
    id            INTEGER PRIMARY KEY,
    astronaut_id  INTEGER NOT NULL REFERENCES astronauts(id),
    start_utc     TEXT NOT NULL,
    end_utc       TEXT NOT NULL,
    deep_min      REAL NOT NULL,
    rem_min       REAL NOT NULL,
    light_min     REAL NOT NULL,
    awake_min     REAL NOT NULL,
    quality_score REAL,
    {_COMMON},
    UNIQUE(astronaut_id, start_utc, source_device)
);
CREATE TABLE IF NOT EXISTS activity_records (
    id                    INTEGER PRIMARY KEY,
    astronaut_id          INTEGER NOT NULL REFERENCES astronauts(id),
    day_utc               TEXT NOT NULL,
    steps                 INTEGER NOT NULL,
    active_min            REAL NOT NULL,
    exercise_min          REAL NOT NULL,
    longest_sedentary_min REAL NOT NULL,
    {_COMMON},
    UNIQUE(astronaut_id, day_utc, source_device)
);
CREATE TABLE IF NOT EXISTS radiation_records (
    id                  INTEGER PRIMARY KEY,
    astronaut_id        INTEGER NOT NULL REFERENCES astronauts(id),
    measured_at_utc     TEXT NOT NULL,
    dose_rate_usv_h     REAL NOT NULL,
    cumulative_dose_msv REAL NOT NULL,
    {_COMMON},
    UNIQUE(astronaut_id, measured_at_utc, source_device)
);
CREATE TABLE IF NOT EXISTS device_connections (
    id             INTEGER PRIMARY KEY,
    device_name    TEXT NOT NULL,
    device_kind    TEXT NOT NULL,
    source_type    TEXT NOT NULL {_SOURCE_CHECK},
    status         TEXT NOT NULL CHECK(status IN ('connected', 'disconnected')),
    changed_at_utc TEXT NOT NULL,
    UNIQUE(device_name, status, changed_at_utc)
);
CREATE TABLE IF NOT EXISTS rejected_inputs (
    id              INTEGER PRIMARY KEY,
    received_at_utc TEXT NOT NULL,
    record_type     TEXT NOT NULL,
    reason          TEXT NOT NULL,
    payload         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS access_log (
    id     INTEGER PRIMARY KEY,
    at_utc TEXT NOT NULL,
    actor  TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS health_baselines (
    id            INTEGER PRIMARY KEY,
    astronaut_id  INTEGER NOT NULL REFERENCES astronauts(id),
    indicator     TEXT NOT NULL,
    day_utc       TEXT NOT NULL,
    median        REAL NOT NULL,
    spread        REAL NOT NULL,
    days_used     INTEGER NOT NULL,
    is_simulated  INTEGER NOT NULL,
    UNIQUE(astronaut_id, indicator, day_utc, is_simulated)
);
CREATE TABLE IF NOT EXISTS health_risk_events (
    id               INTEGER PRIMARY KEY,
    astronaut_id     INTEGER NOT NULL REFERENCES astronauts(id),
    day_utc          TEXT NOT NULL,
    evaluated_at_utc TEXT NOT NULL,
    level            INTEGER NOT NULL CHECK(level BETWEEN 0 AND 4),
    findings         TEXT NOT NULL,
    is_simulated     INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS health_alerts (
    id                   INTEGER PRIMARY KEY,
    astronaut_id         INTEGER NOT NULL REFERENCES astronauts(id),
    code                 TEXT NOT NULL,
    category             TEXT NOT NULL,
    level                INTEGER NOT NULL CHECK(level BETWEEN 1 AND 4),
    message              TEXT NOT NULL,
    created_at_utc       TEXT NOT NULL,
    last_notified_at_utc TEXT,
    notify_count         INTEGER NOT NULL DEFAULT 0,
    acknowledged_at_utc  TEXT,
    is_simulated         INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS health_reports (
    id             INTEGER PRIMARY KEY,
    astronaut_id   INTEGER NOT NULL REFERENCES astronauts(id),
    kind           TEXT NOT NULL,
    day_utc        TEXT NOT NULL,
    level          INTEGER,
    content        TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    is_simulated   INTEGER NOT NULL
);
"""

_RECORD_TABLES = ("health_measurements", "sleep_records", "activity_records", "radiation_records")


@dataclass
class StoreResult:
    inserted: int = 0
    duplicates: int = 0
    rejected: int = 0


class HealthDatabase:
    def __init__(self, path: str | Path = DEFAULT_DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._log = get_astra_logger()
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock, self._conn:
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.executescript(SCHEMA)
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ── Astronot ve görev ────────────────────────────────────────────────
    def add_astronaut(self, name: str) -> int:
        name = (name or "").strip()
        if not name:
            raise InvalidDataError("astronot adı boş")
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO astronauts(name, created_at_utc) VALUES (?, ?)",
                (name, to_utc_iso(utc_now())),
            )
            return self._conn.execute("SELECT id FROM astronauts WHERE name = ?", (name,)).fetchone()["id"]

    def add_mission(self, name: str, start: datetime, local_utc_offset_min: int = 0) -> int:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO mission_records(name, start_utc, local_utc_offset_min) VALUES (?, ?, ?)",
                (name, to_utc_iso(start), int(local_utc_offset_min)),
            )
            return self._conn.execute("SELECT id FROM mission_records WHERE name = ?", (name,)).fetchone()["id"]

    # ── Kayıt ekleme ─────────────────────────────────────────────────────
    def add(self, record, now: datetime | None = None) -> bool:
        """Kaydı doğrulayıp ekler. Eklendiyse True, aynısı zaten varsa False döner.
        Geçersiz kayıt rejected_inputs'a yazılır ve InvalidDataError yükseltilir."""
        with self._lock:
            try:
                return self._add(record, now)
            finally:
                self._conn.commit()

    def add_many(self, records, now: datetime | None = None) -> StoreResult:
        """Kayıtları tek işlemde ekler; geçersiz olanlar reddedilir, diğerleri kaydedilir."""
        result = StoreResult()
        with self._lock:
            try:
                for record in records:
                    try:
                        if self._add(record, now):
                            result.inserted += 1
                        else:
                            result.duplicates += 1
                    except InvalidDataError:
                        result.rejected += 1
            finally:
                self._conn.commit()
        return result

    def _add(self, record, now: datetime | None) -> bool:
        try:
            record.validate(now)
            row = record.row()
        except InvalidDataError as exc:
            self._reject(record, str(exc))
            raise
        row["received_at_utc"] = to_utc_iso(utc_now())
        columns = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        try:
            cur = self._conn.execute(
                f"INSERT OR IGNORE INTO {record.table}({columns}) VALUES ({marks})", tuple(row.values())
            )
            return cur.rowcount == 1
        except sqlite3.IntegrityError as exc:  # ör. kayıtlı olmayan astronot
            self._reject(record, f"veritabanı kısıtı: {exc}")
            raise InvalidDataError(f"veritabanı kısıtı: {exc}") from exc

    def _reject(self, record, reason: str) -> None:
        self._log.warning("Geçersiz veri reddedildi (%s): %s", type(record).__name__, reason)
        self._conn.execute(
            "INSERT INTO rejected_inputs(received_at_utc, record_type, reason, payload) VALUES (?, ?, ?, ?)",
            (to_utc_iso(utc_now()), type(record).__name__, reason,
             json.dumps(asdict(record), default=str, ensure_ascii=False)),
        )

    def add_device_event(self, device_name: str, device_kind: str, source_type: str,
                         status: str, at: datetime) -> None:
        if source_type not in SOURCE_TYPES or status not in ("connected", "disconnected"):
            raise InvalidDataError(f"geçersiz cihaz olayı: {source_type!r}, {status!r}")
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO device_connections(device_name, device_kind, source_type, status, "
                "changed_at_utc) VALUES (?, ?, ?, ?, ?)",
                (device_name, device_kind, source_type, status, to_utc_iso(at)),
            )

    # ── Okuma ────────────────────────────────────────────────────────────
    def _select(self, table: str, time_column: str, astronaut_id: int, start, end,
                simulated, extra: str = "", params: tuple = (), date_only: bool = False) -> list[dict]:
        sql = f"SELECT * FROM {table} WHERE astronaut_id = ?{extra}"
        args = [astronaut_id, *params]
        cut = 10 if date_only else None  # gün sütunları "YYYY-AA-GG" olarak saklanır
        if start is not None:
            sql += f" AND {time_column} >= ?"
            args.append(to_utc_iso(start)[:cut])
        if end is not None:
            sql += f" AND {time_column} < ?"
            args.append(to_utc_iso(end)[:cut])
        if simulated is True:
            sql += " AND source_type = 'SIMULATED'"
        elif simulated is False:
            sql += " AND source_type != 'SIMULATED'"
        sql += f" ORDER BY {time_column}"
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, args).fetchall()]

    def get_measurements(self, astronaut_id: int, metric: str, start: datetime | None = None,
                         end: datetime | None = None, simulated: bool | None = None) -> list[dict]:
        """simulated: True = yalnızca simülasyon, False = yalnızca gerçek, None = hepsi."""
        return self._select("health_measurements", "measured_at_utc", astronaut_id, start, end,
                            simulated, " AND metric = ?", (metric,))

    def get_all_measurements(self, astronaut_id: int, start: datetime | None = None,
                             end: datetime | None = None, simulated: bool | None = None) -> list[dict]:
        return self._select("health_measurements", "measured_at_utc", astronaut_id, start, end, simulated)

    def execute(self, sql: str, params: tuple = ()) -> int:
        """Yazma sorgusu çalıştırır; eklenen satırın kimliğini döndürür."""
        with self._lock, self._conn:
            return self._conn.execute(sql, params).lastrowid

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def device_statuses(self) -> list[dict]:
        """Her cihazın en son bağlantı durumu."""
        return self.query(
            "SELECT d.* FROM device_connections d WHERE d.id = (SELECT id FROM device_connections "
            "WHERE device_name = d.device_name ORDER BY changed_at_utc DESC, id DESC LIMIT 1)")

    def latest_measurement(self, astronaut_id: int, metric: str, simulated: bool | None = None) -> dict | None:
        rows = self.get_measurements(astronaut_id, metric, simulated=simulated)
        return rows[-1] if rows else None

    def get_sleep(self, astronaut_id: int, start=None, end=None, simulated=None) -> list[dict]:
        return self._select("sleep_records", "end_utc", astronaut_id, start, end, simulated)

    def get_activity(self, astronaut_id: int, start=None, end=None, simulated=None) -> list[dict]:
        return self._select("activity_records", "day_utc", astronaut_id, start, end, simulated,
                            date_only=True)

    def get_radiation(self, astronaut_id: int, start=None, end=None, simulated=None) -> list[dict]:
        return self._select("radiation_records", "measured_at_utc", astronaut_id, start, end, simulated)

    def device_status(self, device_name: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM device_connections WHERE device_name = ? ORDER BY changed_at_utc DESC, id DESC LIMIT 1",
                (device_name,),
            ).fetchone()
        return dict(row) if row else None

    # ── Denetim ──────────────────────────────────────────────────────────
    def log_access(self, actor: str, action: str, detail: str = "") -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO access_log(at_utc, actor, action, detail) VALUES (?, ?, ?, ?)",
                (to_utc_iso(utc_now()), actor, action, detail),
            )

    def counts(self) -> dict[str, int]:
        tables = _RECORD_TABLES + ("device_connections", "rejected_inputs", "access_log")
        with self._lock:
            return {t: self._conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}

    def simulated_counts(self) -> dict[str, int]:
        with self._lock:
            return {
                t: self._conn.execute(f"SELECT COUNT(*) FROM {t} WHERE source_type = 'SIMULATED'").fetchone()[0]
                for t in _RECORD_TABLES
            }

    def integrity_ok(self) -> bool:
        with self._lock:
            return self._conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
