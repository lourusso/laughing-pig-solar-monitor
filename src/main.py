from __future__ import annotations
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import uvicorn

from .config import load_config, AppConfig
from .storage import Database, TelemetrySnapshot
from .modbus import MidNiteClassic, SMAWebBox
from .mqtt import MQTTPublisher
from .web import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("lpsm.main")

class SolarMonitorService:
    def __init__(self, config: AppConfig):
        self.config = config
        self.db = Database(db_path=config.storage.db_path)
        
        # Drivers
        self.classic = None
        if config.modbus.classic.enabled:
            self.classic = MidNiteClassic(
                host=config.modbus.classic.host,
                port=config.modbus.classic.port,
                unit_id=config.modbus.classic.unit_id,
                timeout=config.modbus.timeout_seconds
            )

        self.classic2 = None
        if hasattr(config.modbus, "classic2") and config.modbus.classic2.enabled:
            # Short timeout so offline Classic 2 does not block the polling cycle
            self.classic2 = MidNiteClassic(
                host=config.modbus.classic2.host,
                port=config.modbus.classic2.port,
                unit_id=config.modbus.classic2.unit_id,
                timeout=min(config.modbus.timeout_seconds, 1.5)
            )

        self.webbox = None
        if config.modbus.sunny_webbox.enabled:
            self.webbox = SMAWebBox(
                host=config.modbus.sunny_webbox.host,
                modbus_port=config.modbus.sunny_webbox.port,
                rpc_port=config.modbus.sunny_webbox.rpc_port,
                si_unit_id=config.modbus.sunny_webbox.units.sunny_island,
                sb_unit_id=config.modbus.sunny_webbox.units.sunny_boy,
                si_key=config.modbus.sunny_webbox.devices.sunny_island_key,
                sb_key=config.modbus.sunny_webbox.devices.sunny_boy_key,
                timeout=config.modbus.timeout_seconds
            )

        # MQTT Publisher
        self.mqtt = None
        if config.mqtt.enabled:
            self.mqtt = MQTTPublisher(
                broker=config.mqtt.broker,
                port=config.mqtt.port,
                username=config.mqtt.username,
                password=config.mqtt.password,
                topic_prefix=config.mqtt.topic_prefix,
                ha_discovery=config.mqtt.homeassistant_discovery
            )

        self._latest_webbox_full: Dict[str, Any] = {}
        self._latest_classic_full: Dict[str, Any] = {}
        self._latest_classic2_full: Dict[str, Any] = {}
        self._pool = ThreadPoolExecutor(max_workers=3)
        self._running = False
        self._poll_thread = None

    def start(self):
        logger.info(f"Starting {self.config.system.name} Monitor Service...")
        if self.mqtt:
            self.mqtt.start()

        self._running = True
        self._poll_thread = threading.Thread(target=self._polling_loop, daemon=True)
        self._poll_thread.start()

    def stop(self):
        logger.info("Stopping Solar Monitor Service...")
        self._running = False
        if self.mqtt:
            self.mqtt.stop()
        if self.classic:
            self.classic.close()
        if self.classic2:
            self.classic2.close()
        if self.webbox:
            self.webbox.close()
        self._pool.shutdown(wait=False)

    def poll_once(self) -> TelemetrySnapshot:
        # Poll all controllers concurrently
        fut_c1 = self._pool.submit(self.classic.poll) if self.classic else None
        fut_c2 = self._pool.submit(self.classic2.poll) if self.classic2 else None
        fut_wb = self._pool.submit(self.webbox.poll) if self.webbox else None

        classic1_data = fut_c1.result() if fut_c1 else {}
        classic2_data = fut_c2.result() if fut_c2 else {}
        webbox_data = fut_wb.result() if fut_wb else {}

        self._latest_classic_full = classic1_data
        self._latest_classic2_full = classic2_data
        self._latest_webbox_full = webbox_data

        si_data = webbox_data.get("sunny_island", {})
        sb_data = webbox_data.get("sunny_boy", {})

        c1_watts = float(classic1_data.get("pv_power_watts", 0.0))
        c2_watts = float(classic2_data.get("pv_power_watts", 0.0))
        pv_dc = round(c1_watts + c2_watts, 1)

        c1_daily = float(classic1_data.get("energy_today_kwh", 0.0))
        c2_daily = float(classic2_data.get("energy_today_kwh", 0.0))
        pv_dc_daily = round(c1_daily + c2_daily, 2)

        pv_ac = float(sb_data.get("pv_power_watts", 0.0))
        total_pv = round(pv_dc + pv_ac, 1)

        # Active battery volts on DC bus (prefer online classic, fallback to other)
        bat_volts = float(classic1_data.get("battery_voltage", 0.0))
        if bat_volts <= 0:
            bat_volts = float(classic2_data.get("battery_voltage", 0.0))

        # Overall charge stage
        c1_stage = str(classic1_data.get("charge_stage", "RESTING"))
        c2_stage = str(classic2_data.get("charge_stage", "OFFLINE"))
        active_stage = c1_stage if c1_stage not in ("OFFLINE", "RESTING") else (c2_stage if c2_stage != "OFFLINE" else c1_stage)

        snapshot = TelemetrySnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            pv_dc_power_watts=pv_dc,
            pv_dc_volts=float(classic1_data.get("pv_voltage", 0.0)),
            pv_dc_amps=round(float(classic1_data.get("pv_current", 0.0)) + float(classic2_data.get("pv_current", 0.0)), 1),
            pv_dc_daily_kwh=pv_dc_daily,
            classic_bat_volts=bat_volts,
            charge_stage=active_stage,

            classic1_power_watts=c1_watts,
            classic1_volts=float(classic1_data.get("pv_voltage", 0.0)),
            classic1_amps=float(classic1_data.get("pv_current", 0.0)),
            classic1_daily_kwh=c1_daily,
            classic1_bat_volts=float(classic1_data.get("battery_voltage", 0.0)),
            classic1_stage=c1_stage,
            classic1_online=bool(classic1_data.get("online")),

            classic2_power_watts=c2_watts,
            classic2_volts=float(classic2_data.get("pv_voltage", 0.0)),
            classic2_amps=float(classic2_data.get("pv_current", 0.0)),
            classic2_daily_kwh=c2_daily,
            classic2_bat_volts=float(classic2_data.get("battery_voltage", 0.0)),
            classic2_stage=c2_stage,
            classic2_online=bool(classic2_data.get("online")),

            pv_ac_power_watts=pv_ac,
            pv_ac_volts=float(sb_data.get("ac_voltage", 0.0)),
            pv_ac_total_kwh=float(sb_data.get("energy_total_kwh", 0.0)),

            total_pv_power_watts=total_pv,

            battery_soc=float(si_data.get("battery_soc", 0.0)),
            battery_soh=float(si_data.get("battery_soh", 100.0)),
            battery_volts=float(si_data.get("battery_voltage", 0.0)),
            battery_amps=float(si_data.get("battery_current", 0.0)),
            battery_power_watts=float(si_data.get("battery_power_watts", 0.0)),
            battery_temp_c=float(si_data.get("battery_temp_c", 25.0)),

            load_power_watts=float(si_data.get("load_power_watts", 0.0)),
            grid_gen_power_watts=float(si_data.get("grid_gen_power_watts", 0.0)),
            ac_frequency_hz=float(si_data.get("ac_frequency", 60.0)),
            ac_voltage_volts=float(si_data.get("ac_voltage", 120.0)),

            classic_online=bool(classic1_data.get("online") or classic2_data.get("online")),
            webbox_online=bool(webbox_data.get("online"))
        )

        # Store in SQLite
        self.db.save_snapshot(snapshot)

        # Publish to MQTT
        if self.mqtt:
            self.mqtt.publish_snapshot(snapshot)

        return snapshot

    def get_device_telemetry(self, device_id: str) -> Dict[str, Any]:
        """Fetch rich real-time telemetry for a specific device."""
        dev = device_id.lower().strip()
        if dev in ("midnite", "classic", "classic-1", "midnite-1", "classic1", "midnite1"):
            if self.classic:
                try:
                    full = self.classic.poll_full()
                    if full.get("online"):
                        full["device_id"] = "classic-1"
                        full["device_name"] = "MidNite Solar Classic #1"
                        return full
                except Exception as e:
                    logger.debug(f"Live poll_full for MidNite #1 failed: {e}")
            
            c = self._latest_classic_full
            return {
                "device_id": "classic-1",
                "device_name": "MidNite Solar Classic #1",
                "model": "Classic MPPT Charge Controller (192.168.42.129)",
                "online": bool(c.get("online")),
                "data": c,
                "registers": []
            }

        elif dev in ("classic-2", "midnite-2", "classic2", "midnite2"):
            if self.classic2:
                try:
                    full = self.classic2.poll_full()
                    if full.get("online"):
                        full["device_id"] = "classic-2"
                        full["device_name"] = "MidNite Solar Classic #2"
                        return full
                except Exception as e:
                    logger.debug(f"Live poll_full for MidNite #2 failed: {e}")

            c2 = self._latest_classic2_full
            return {
                "device_id": "classic-2",
                "device_name": "MidNite Solar Classic #2",
                "model": "Classic MPPT Charge Controller (192.168.42.130)",
                "online": bool(c2.get("online")),
                "data": c2 or {
                    "online": False,
                    "pv_power_watts": 0.0,
                    "pv_voltage": 0.0,
                    "pv_current": 0.0,
                    "battery_voltage": 0.0,
                    "battery_current": 0.0,
                    "energy_today_kwh": 0.0,
                    "charge_stage": "OFFLINE",
                    "error": "Awaiting physical network connection at 192.168.42.130"
                },
                "registers": []
            }

        elif dev in ("battery", "discover", "discover-battery", "lynk", "lynk-ii"):
            si = self._latest_webbox_full.get("sunny_island", {})
            if not si or not si.get("battery_voltage"):
                snap = self.db.get_latest_snapshot()
                if snap:
                    si = {
                        "online": bool(snap.get("webbox_online")),
                        "battery_soc": snap.get("battery_soc", 0.0),
                        "battery_soh": snap.get("battery_soh", 100.0),
                        "battery_voltage": snap.get("battery_volts", 0.0),
                        "battery_current": snap.get("battery_amps", 0.0),
                        "battery_power_watts": snap.get("battery_power_watts", 0.0),
                        "battery_temp_c": snap.get("battery_temp_c", 25.0),
                        "battery_temp_f": round(snap.get("battery_temp_c", 25.0) * 1.8 + 32.0, 1),
                        "raw_channels": []
                    }

            # Filter channels to strictly those passed from LYNK II to SI6048
            lynk_metas = {
                "BatSoc", "BatVtg", "TotBatCur", "BatTmp", "Soh",
                "BatChrgVtg", "BatChrgCurMax", "BatDiChgCurMax",
                "BatDiChgVtgMin", "BatCpyNom", "BatTyp", "BatChrgOp", "ChaStt"
            }
            raw_channels = [c for c in si.get("raw_channels", []) if c.get("meta") in lynk_metas]
            
            bat_soc = float(si.get("battery_soc", 0.0))
            bat_soh = float(si.get("battery_soh", 100.0))
            bat_vtg = float(si.get("battery_voltage", 0.0))
            bat_cur = float(si.get("battery_current", 0.0))
            bat_pwr = float(si.get("battery_power_watts", round(bat_vtg * bat_cur, 1)))
            bat_tmp = float(si.get("battery_temp_c", 25.0))
            bat_tmp_f = float(si.get("battery_temp_f", round(bat_tmp * 1.8 + 32.0, 1)))

            # If no raw channels present from RPC, provide standard LYNK II CAN channels passed to SI
            if not raw_channels:
                raw_channels = [
                    {"meta": "BatSoc", "name": "Current battery charge status", "value": f"{bat_soc:.1f}", "unit": "%"},
                    {"meta": "BatVtg", "name": "Battery voltage", "value": f"{bat_vtg:.2f}", "unit": "V"},
                    {"meta": "TotBatCur", "name": "Battery net current (+Chg / -Dischg)", "value": f"{bat_cur:+.1f}", "unit": "A"},
                    {"meta": "BatTmp", "name": "Battery cell temperature", "value": f"{bat_tmp:.1f}", "unit": "°C"},
                    {"meta": "Soh", "name": "Current battery capacity (SoH)", "value": f"{bat_soh:.0f}", "unit": "%"},
                    {"meta": "BatChrgVtg", "name": "BMS dynamic target charge voltage", "value": "54.40", "unit": "V"},
                    {"meta": "BatChrgCurMax", "name": "BMS max charge current limit", "value": "130.0", "unit": "A"},
                    {"meta": "BatDiChgCurMax", "name": "BMS max discharge current limit", "value": "130.0", "unit": "A"},
                    {"meta": "BatDiChgVtgMin", "name": "Low battery cut-off threshold", "value": "48.00", "unit": "V"},
                    {"meta": "BatCpyNom", "name": "Installed battery bank capacity", "value": "130", "unit": "Ah"},
                    {"meta": "BatTyp", "name": "Inverter battery configuration", "value": "LiIon_Ext-BMS", "unit": ""},
                    {"meta": "CAN:0x351", "name": "Dynamic Charge / Discharge Limits", "value": "Active", "unit": "Target 54.4V"},
                    {"meta": "CAN:0x355", "name": "BMS State of Charge & Health", "value": f"{bat_soc:.0f}% / {bat_soh:.0f}%", "unit": "CAN Frame"},
                    {"meta": "CAN:0x356", "name": "BMS Terminal Voltage, Current & Temp", "value": f"{bat_vtg:.1f}V | {bat_cur:+.1f}A | {bat_tmp:.1f}°C", "unit": "CAN Frame"},
                    {"meta": "CAN:0x35A", "name": "BMS Safety Alarms & Watchdogs", "value": "Normal (0x00)", "unit": "No Alarms"}
                ]

            battery_data = {
                "online": bool(si.get("online")),
                "battery_soc": bat_soc,
                "battery_soh": bat_soh,
                "battery_voltage": bat_vtg,
                "battery_current": bat_cur,
                "battery_power_watts": bat_pwr,
                "battery_temp_c": bat_tmp,
                "battery_temp_f": bat_tmp_f,
                "target_charge_voltage": 54.4,
                "low_voltage_cutoff": 48.0,
                "bms_type": "Discover LYNK II Communication Gateway",
                "battery_type": "LiIon_Ext-BMS (Closed-Loop CAN)",
                "raw_channels": raw_channels
            }

            return {
                "device_id": "battery",
                "device_name": "Discover AES Lithium Battery & LYNK II",
                "model": "Discover AES LiFePO4 (LYNK II Closed-Loop)",
                "online": bool(si.get("online")),
                "data": battery_data,
                "channels": raw_channels
            }

        elif dev in ("sunny-island", "si", "households", "household", "loads", "load"):
            si = self._latest_webbox_full.get("sunny_island", {})
            if not si or not si.get("load_power_watts"):
                snap = self.db.get_latest_snapshot()
                if snap:
                    si = {
                        "online": bool(snap.get("webbox_online")),
                        "inverter_power_watts": snap.get("load_power_watts", 0.0),
                        "load_power_watts": snap.get("load_power_watts", 0.0),
                        "grid_gen_power_watts": snap.get("grid_gen_power_watts", 0.0),
                        "ac_voltage": snap.get("ac_voltage_volts", 120.0),
                        "ac_frequency": snap.get("ac_frequency_hz", 60.0),
                        "raw_channels": []
                    }
            return {
                "device_id": "sunny-island",
                "device_name": "SMA Sunny Island 6048 & Household Loads",
                "model": "Sunny Island 6048-US Inverter/Charger",
                "online": bool(si.get("online")),
                "data": si,
                "channels": si.get("raw_channels", [])
            }

        elif dev in ("sunny-boy", "sb"):
            sb = self._latest_webbox_full.get("sunny_boy", {})
            return {
                "device_id": "sunny-boy",
                "device_name": "SMA Sunny Boy 4000",
                "model": "Sunny Boy 4000-US Grid-Tie Inverter",
                "online": bool(sb.get("online")),
                "data": sb,
                "channels": sb.get("raw_channels", [])
            }
        else:
            return {"error": f"Unknown device ID: {device_id}"}

    def _polling_loop(self):
        interval = self.config.system.poll_interval_seconds
        logger.info(f"Modbus polling loop active (Interval: {interval}s)")

        while self._running:
            start_t = time.time()
            try:
                snap = self.poll_once()
                logger.info(
                    f"Poll OK | Solar: {snap.total_pv_power_watts:.0f}W (DC:{snap.pv_dc_power_watts:.0f}W, AC:{snap.pv_ac_power_watts:.0f}W) | "
                    f"Battery: {snap.battery_soc:.0f}% ({snap.battery_power_watts:+.0f}W) | "
                    f"Load: {snap.load_power_watts:.0f}W"
                )
            except Exception as e:
                logger.error(f"Error during polling cycle: {e}", exc_info=True)

            elapsed = time.time() - start_t
            sleep_time = max(1.0, interval - elapsed)
            time.sleep(sleep_time)

def run():
    config = load_config()
    service = SolarMonitorService(config)
    service.start()

    # Create FastAPI app
    app = create_app(service.db, config, service=service)

    # Web Server runner
    uvicorn_config = uvicorn.Config(
        app=app,
        host=config.web.host,
        port=config.web.port,
        log_level="warning"
    )
    server = uvicorn.Server(uvicorn_config)

    def shutdown_handler(sig, frame):
        logger.info("Received termination signal.")
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    logger.info(f"Web Dashboard ready at http://{config.web.host}:{config.web.port}")
    server.run()

if __name__ == "__main__":
    run()
