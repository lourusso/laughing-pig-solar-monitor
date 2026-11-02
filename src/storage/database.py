import io
import csv
import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from .models import TelemetrySnapshot

logger = logging.getLogger(__name__)

# Cutoff timestamp for our fresh history start:
# Today (2026-11-01) at 3:15 PM Hawaii Standard Time (-10:00) is 2026-11-02T01:15:00+00:00 in UTC!
HISTORY_RESET_KEY = "history_reset_20261101_1515"
HISTORY_RESET_CUTOFF_UTC = "2026-11-02T01:15:00+00:00"

# ==============================================================================
# Database: The Farm's Electronic Solar Diary!
# ==============================================================================
# Every few seconds, our monitor takes a quick snapshot of the entire farm.
# This Database class is our faithful scribe: it writes down every single reading
# into a neat, organized SQLite notebook on the disk (`data/solar.db`).
# That way, we can look back and see how much sunshine we harvested yesterday,
# last week, or even three months ago!
# ==============================================================================

class Database:
    def __init__(self, db_path: str = "data/solar.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Keep our solar diary open on the desk (`self._conn`) with a polite
        # talking stick (`self._lock`) so threads take turns without opening
        # and closing the file cover every few seconds!
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        # Fast RAM cache for historical chart queries (`/api/history`)
        self._history_cache: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        # Think of this connection like keeping our notebook open on the desk
        # instead of putting it back in the backpack after every single sentence!
        if self._conn is None:
            conn = sqlite3.connect(str(self.db_path), timeout=10.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            # "PRAGMA synchronous=NORMAL" is like telling the notebook:
            # "Write neatly and safely, but don't pause to lock the notebook in a safe after every single letter."
            # This makes the database work much faster while keeping your data safe!
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA temp_store=MEMORY;")
            conn.execute("PRAGMA cache_size=-8000;")  # 8MB RAM page cache
            self._conn = conn
        return self._conn

    def _init_db(self):
        # We set up the notebook rules once right here when the monitor first turns on.
        with self._lock:
            conn = self._get_connection()
            # WAL mode means "Write-Ahead Logging".
            # Imagine writing quick sticky notes first, then filing them neatly in the notebook.
            # It lets us read and write at the very same time without bumping into each other!
            # SQLite remembers WAL mode forever in the file, so we only need to turn it on once here.
            conn.execute("PRAGMA journal_mode=WAL;")
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT UNIQUE NOT NULL,
                    pv_dc_power_watts REAL,
                    pv_dc_volts REAL,
                    pv_dc_amps REAL,
                    pv_dc_daily_kwh REAL,
                    classic_bat_volts REAL,
                    charge_stage TEXT,
                    pv_ac_power_watts REAL,
                    pv_ac_volts REAL,
                    pv_ac_total_kwh REAL,
                    total_pv_power_watts REAL,
                    battery_soc REAL,
                    battery_soh REAL,
                    battery_volts REAL,
                    battery_amps REAL,
                    battery_power_watts REAL,
                    battery_temp_c REAL,
                    load_power_watts REAL,
                    grid_gen_power_watts REAL,
                    ac_frequency_hz REAL,
                    ac_voltage_volts REAL,
                    classic_online INTEGER,
                    webbox_online INTEGER,
                    warnings TEXT
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_time ON snapshots (timestamp);")

            # Migrations for dual MidNite Classic, eGauge Farm Loads, and Fahrenheit support
            classic_cols = [
                ("classic_bat_volts", "REAL DEFAULT 0.0"),
                ("classic1_power_watts", "REAL DEFAULT 0.0"),
                ("classic1_volts", "REAL DEFAULT 0.0"),
                ("classic1_amps", "REAL DEFAULT 0.0"),
                ("classic1_daily_kwh", "REAL DEFAULT 0.0"),
                ("classic1_bat_volts", "REAL DEFAULT 0.0"),
                ("classic1_stage", "TEXT DEFAULT 'RESTING'"),
                ("classic1_online", "INTEGER DEFAULT 0"),
                ("classic2_power_watts", "REAL DEFAULT 0.0"),
                ("classic2_volts", "REAL DEFAULT 0.0"),
                ("classic2_amps", "REAL DEFAULT 0.0"),
                ("classic2_daily_kwh", "REAL DEFAULT 0.0"),
                ("classic2_bat_volts", "REAL DEFAULT 0.0"),
                ("classic2_stage", "TEXT DEFAULT 'OFFLINE'"),
                ("classic2_online", "INTEGER DEFAULT 0"),
                ("sunnyboy_online", "INTEGER DEFAULT 0"),
                ("generator_volts", "REAL DEFAULT 0.0"),
                ("generator_amps", "REAL DEFAULT 0.0"),
                ("generator_frequency", "REAL DEFAULT 0.0"),
                ("egauge_online", "INTEGER DEFAULT 0"),
                ("house_load_watts", "REAL DEFAULT 0.0"),
                ("shop_load_watts", "REAL DEFAULT 0.0"),
                ("load_source", "TEXT DEFAULT 'eGauge S1'"),
                ("battery_temp_f", "REAL DEFAULT 77.0"),
            ]
            for col_name, col_def in classic_cols:
                try:
                    conn.execute(f"ALTER TABLE snapshots ADD COLUMN {col_name} {col_def};")
                except sqlite3.OperationalError:
                    pass

            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_summaries (
                    date TEXT PRIMARY KEY,
                    pv_dc_kwh REAL,
                    pv_ac_kwh REAL,
                    total_pv_kwh REAL,
                    min_battery_soc REAL,
                    max_battery_soc REAL,
                    peak_pv_power_watts REAL,
                    peak_load_power_watts REAL
                );
            """)

            # System metadata table to remember one-time upgrades and cleanups
            conn.execute("""
                CREATE TABLE IF NOT EXISTS system_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
            """)

            # One-time fresh start at 3:15 PM today (2026-11-01 15:15 HST / 2026-11-02T01:15:00+00:00 UTC)
            # Now that Farm Loads and Fahrenheit temperatures are accurate, we sweep away
            # any older historical readings prior to 3:15 PM today!
            cur = conn.execute("SELECT value FROM system_meta WHERE key = ?;", (HISTORY_RESET_KEY,))
            if cur.fetchone() is None:
                del_cur = conn.execute(
                    "DELETE FROM snapshots WHERE timestamp < ?;",
                    (HISTORY_RESET_CUTOFF_UTC,)
                )
                conn.execute("DELETE FROM daily_summaries;")
                conn.execute(
                    "INSERT OR REPLACE INTO system_meta (key, value) VALUES (?, ?);",
                    (HISTORY_RESET_KEY, HISTORY_RESET_CUTOFF_UTC)
                )
                conn.commit()
                logger.info(
                    f"Cleared {del_cur.rowcount} historical snapshots prior to 3:15 PM today ({HISTORY_RESET_CUTOFF_UTC})."
                )
            else:
                conn.commit()

    def save_snapshot(self, snapshot: TelemetrySnapshot) -> None:
        """
        Write a brand-new page into our electronic solar diary!
        Every sensor reading from the snapshot gets filed neatly into its own column.
        """
        sql = """
            INSERT OR REPLACE INTO snapshots (
                timestamp, pv_dc_power_watts, pv_dc_volts, pv_dc_amps, pv_dc_daily_kwh,
                classic_bat_volts, charge_stage,
                classic1_power_watts, classic1_volts, classic1_amps, classic1_daily_kwh,
                classic1_bat_volts, classic1_stage, classic1_online,
                classic2_power_watts, classic2_volts, classic2_amps, classic2_daily_kwh,
                classic2_bat_volts, classic2_stage, classic2_online,
                pv_ac_power_watts, pv_ac_volts, pv_ac_total_kwh,
                total_pv_power_watts, battery_soc, battery_soh, battery_volts,
                battery_amps, battery_power_watts, battery_temp_c, battery_temp_f,
                load_power_watts,
                grid_gen_power_watts, generator_volts, generator_amps, generator_frequency,
                ac_frequency_hz, ac_voltage_volts,
                classic_online, webbox_online, sunnyboy_online,
                egauge_online, house_load_watts, shop_load_watts, load_source,
                warnings
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        try:
            with self._lock:
                conn = self._get_connection()
                conn.execute(sql, (
                    snapshot.timestamp,
                    snapshot.pv_dc_power_watts,
                    snapshot.pv_dc_volts,
                    snapshot.pv_dc_amps,
                    snapshot.pv_dc_daily_kwh,
                    snapshot.classic_bat_volts,
                    snapshot.charge_stage,
                    snapshot.classic1_power_watts,
                    snapshot.classic1_volts,
                    snapshot.classic1_amps,
                    snapshot.classic1_daily_kwh,
                    snapshot.classic1_bat_volts,
                    snapshot.classic1_stage,
                    1 if snapshot.classic1_online else 0,
                    snapshot.classic2_power_watts,
                    snapshot.classic2_volts,
                    snapshot.classic2_amps,
                    snapshot.classic2_daily_kwh,
                    snapshot.classic2_bat_volts,
                    snapshot.classic2_stage,
                    1 if snapshot.classic2_online else 0,
                    snapshot.pv_ac_power_watts,
                    snapshot.pv_ac_volts,
                    snapshot.pv_ac_total_kwh,
                    snapshot.total_pv_power_watts,
                    snapshot.battery_soc,
                    snapshot.battery_soh,
                    snapshot.battery_volts,
                    snapshot.battery_amps,
                    snapshot.battery_power_watts,
                    snapshot.battery_temp_c,
                    snapshot.battery_temp_f,
                    snapshot.load_power_watts,
                    snapshot.grid_gen_power_watts,
                    snapshot.generator_volts,
                    snapshot.generator_amps,
                    snapshot.generator_frequency,
                    snapshot.ac_frequency_hz,
                    snapshot.ac_voltage_volts,
                    1 if snapshot.classic_online else 0,
                    1 if snapshot.webbox_online else 0,
                    1 if snapshot.sunnyboy_online else 0,
                    1 if snapshot.egauge_online else 0,
                    snapshot.house_load_watts,
                    snapshot.shop_load_watts,
                    snapshot.load_source,
                    snapshot.warnings
                ))
                conn.commit()
                # Clear our RAM chart cache so the next chart request sees the new point!
                self._history_cache.clear()
        except Exception as e:
            logger.error(f"Error saving snapshot to database: {e}")

    def get_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        """
        Open the solar diary to the very last page!
        This gives us the most recent snapshot so we know what the farm is doing right now.
        """
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute("SELECT * FROM snapshots ORDER BY id DESC LIMIT 1;")
            row = cur.fetchone()
            if not row:
                return None
            data = dict(row)
            # If the database row doesn't have Fahrenheit yet, calculate it from Celsius!
            # (Celsius * 1.8) + 32 = Fahrenheit
            if "battery_temp_f" not in data or data["battery_temp_f"] is None:
                c = data.get("battery_temp_c", 25.0) or 25.0
                data["battery_temp_f"] = round(c * 1.8 + 32.0, 1)
            return data

    def get_history(self, hours: int = 24, max_points: int = 300) -> List[Dict[str, Any]]:
        """
        Fetch historical records over the last few hours to draw charts and graphs.
        Uses our fast RAM cache (`self._history_cache`) so multiple browsers can view
        charts without making the hard drive work!
        """
        cache_key = (hours, max_points)
        with self._lock:
            if cache_key in self._history_cache:
                return self._history_cache[cache_key]

            since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            conn = self._get_connection()
            cur = conn.execute("""
                SELECT timestamp, total_pv_power_watts, pv_dc_power_watts, pv_ac_power_watts,
                       classic1_power_watts, classic2_power_watts,
                       battery_power_watts, battery_soc, load_power_watts, grid_gen_power_watts,
                       battery_volts
                FROM snapshots
                WHERE timestamp >= ?
                ORDER BY timestamp ASC;
            """, (since,))
            # Fetch raw database rows first without making thousands of temporary dictionaries.
            rows = cur.fetchall()

            if not rows:
                res: List[Dict[str, Any]] = []
            elif len(rows) <= max_points:
                # If we only have a few points, convert all of them into easy-to-read dictionaries.
                res = [dict(r) for r in rows]
            else:
                # Imagine you took 8,640 photos on a long summer road trip, but your photo album only holds 300 photos.
                # Instead of making 8,640 expensive photo prints and throwing 8,340 in the trash,
                # we pick only 300 evenly spaced photos across the day!
                # This saves computer memory and makes the graphs pop up lightning fast!
                step = len(rows) / max_points
                res = [dict(rows[int(i * step)]) for i in range(max_points)]

            self._history_cache[cache_key] = res
            return res

    def export_csv(self, days: int = 7) -> str:
        """
        Export our diary records into a CSV spreadsheet!
        You can open this file directly in Excel, Numbers, or Google Sheets to see the raw data.
        """
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute("SELECT * FROM snapshots WHERE timestamp >= ? ORDER BY timestamp ASC;", (since,))
            rows = cur.fetchall()

            output = io.StringIO()
            if rows:
                writer = csv.writer(output)
                writer.writerow(rows[0].keys())
                for r in rows:
                    writer.writerow(tuple(r))
            return output.getvalue()

    def prune_old_snapshots(self, retention_days: int = 90) -> int:
        # This is our little database janitor!
        # It tidies up by sweeping away any solar snapshots older than 90 days.
        # That way our computer storage never gets full of stale, dusty data!
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute("DELETE FROM snapshots WHERE timestamp < ?;", (cutoff,))
            conn.commit()
            if cur.rowcount > 0:
                self._history_cache.clear()
            return cur.rowcount

    def close(self) -> None:
        """Close the persistent SQLite connection cleanly when shutting down."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
