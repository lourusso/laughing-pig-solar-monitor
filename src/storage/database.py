import io
import csv
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from .models import TelemetrySnapshot

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str = "data/solar.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for high-concurrency read/write
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
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

            # Migrations for dual MidNite Classic support
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
            conn.commit()

    def save_snapshot(self, snapshot: TelemetrySnapshot) -> None:
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
                battery_amps, battery_power_watts, battery_temp_c, load_power_watts,
                grid_gen_power_watts, ac_frequency_hz, ac_voltage_volts,
                classic_online, webbox_online, warnings
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        try:
            with self._get_connection() as conn:
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
                    snapshot.load_power_watts,
                    snapshot.grid_gen_power_watts,
                    snapshot.ac_frequency_hz,
                    snapshot.ac_voltage_volts,
                    1 if snapshot.classic_online else 0,
                    1 if snapshot.webbox_online else 0,
                    snapshot.warnings
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving snapshot to database: {e}")

    def get_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM snapshots ORDER BY id DESC LIMIT 1;")
            row = cur.fetchone()
            return dict(row) if row else None

    def get_history(self, hours: int = 24, max_points: int = 300) -> List[Dict[str, Any]]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._get_connection() as conn:
            cur = conn.execute("""
                SELECT timestamp, total_pv_power_watts, pv_dc_power_watts, pv_ac_power_watts,
                       battery_power_watts, battery_soc, load_power_watts, grid_gen_power_watts,
                       battery_volts
                FROM snapshots
                WHERE timestamp >= ?
                ORDER BY timestamp ASC;
            """, (since,))
            rows = [dict(r) for r in cur.fetchall()]

            if len(rows) <= max_points or not rows:
                return rows

            # Downsample evenly to avoid overloading charts
            step = len(rows) / max_points
            return [rows[int(i * step)] for i in range(max_points)]

    def export_csv(self, days: int = 7) -> str:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._get_connection() as conn:
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
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM snapshots WHERE timestamp < ?;", (cutoff,))
            conn.commit()
            return cur.rowcount
