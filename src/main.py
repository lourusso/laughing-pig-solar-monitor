from __future__ import annotations
import asyncio
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
        if self.webbox:
            self.webbox.close()

    def poll_once(self) -> TelemetrySnapshot:
        classic_data = self.classic.poll() if self.classic else {}
        webbox_data = self.webbox.poll() if self.webbox else {}
        self._latest_classic_full = classic_data
        self._latest_webbox_full = webbox_data

        si_data = webbox_data.get("sunny_island", {})
        sb_data = webbox_data.get("sunny_boy", {})

        pv_dc = float(classic_data.get("pv_power_watts", 0.0))
        pv_ac = float(sb_data.get("pv_power_watts", 0.0))
        total_pv = round(pv_dc + pv_ac, 1)

        snapshot = TelemetrySnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            pv_dc_power_watts=pv_dc,
            pv_dc_volts=float(classic_data.get("pv_voltage", 0.0)),
            pv_dc_amps=float(classic_data.get("pv_current", 0.0)),
            pv_dc_daily_kwh=float(classic_data.get("energy_today_kwh", 0.0)),
            classic_bat_volts=float(classic_data.get("battery_voltage", 0.0)),
            charge_stage=str(classic_data.get("charge_stage", "RESTING")),

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

            classic_online=bool(classic_data.get("online")),
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
        if dev in ("midnite", "classic"):
            if self.classic:
                try:
                    full = self.classic.poll_full()
                    if full.get("online"):
                        return full
                except Exception as e:
                    logger.debug(f"Live poll_full for MidNite failed: {e}")
            
            c = self._latest_classic_full
            return {
                "device_id": "midnite",
                "device_name": "MidNite Solar Classic",
                "model": "Classic MPPT Charge Controller",
                "online": bool(c.get("online")),
                "data": c,
                "registers": []
            }

        elif dev in ("sunny-island", "battery", "si", "ess", "discover", "discover-battery"):
            si = self._latest_webbox_full.get("sunny_island", {})
            return {
                "device_id": "sunny-island",
                "device_name": "Discover AES Lithium & SMA Sunny Island 6048",
                "model": "Discover AES LiFePO4 + SI 6048-US (LYNK II Closed-Loop)",
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
