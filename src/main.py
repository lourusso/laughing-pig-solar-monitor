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
from .egauge import EGaugeClient
from .mqtt import MQTTPublisher
from .web import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("lpsm.main")

# ==============================================================================
# Solar Monitor Service: The Farm's Orchestra Conductor!
# ==============================================================================
# Imagine our solar farm is a musical orchestra:
# - The MidNite Classics are playing the sunny brass instruments (DC Solar).
# - The Sunny Boy is playing the electric guitar (AC Solar in the shop).
# - The Sunny Island & Discover Battery are playing the drums (keeping the rhythm).
# - The eGauge is listening with its stethoscope to make sure everyone sounds great!
#
# SolarMonitorService is the Conductor! It leads all the musicians:
# Every few seconds, it asks each gadget for their latest numbers, combines them
# into one neat snapshot, writes the story in the database diary, and paints
# the live dashboard on our computer and phone screens!
# ==============================================================================

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
            self.classic2 = MidNiteClassic(
                host=config.modbus.classic2.host,
                port=config.modbus.classic2.port,
                unit_id=config.modbus.classic2.unit_id,
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

        # eGauge EG3010 Energy Meter
        self.egauge = None
        if hasattr(config, "egauge") and config.egauge.enabled:
            self.egauge = EGaugeClient(
                host=config.egauge.host,
                port=config.egauge.port,
                timeout=config.egauge.timeout_seconds,
                mac_address=config.egauge.mac_address
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
        self._latest_egauge_full: Dict[str, Any] = {}

        # Quick-memory scratchpad (In-Memory Telemetry Cache):
        # We keep the newest solar snapshot right in fast computer memory (RAM).
        # When someone looks at the dashboard, we can hand them the answer instantly
        # without making the computer search through the hard drive!
        self._latest_snapshot: Optional[TelemetrySnapshot] = None
        self._latest_snapshot_dict: Optional[Dict[str, Any]] = None
        try:
            self._latest_snapshot_dict = self.db.get_latest_snapshot()
        except Exception:
            self._latest_snapshot_dict = None

        # Device details cache:
        # Think of this like a temporary sticky note for each gadget.
        # We remember the detailed numbers for 10 seconds so we don't bombard
        # the small computer chips on the charge controllers every 3 seconds!
        self._device_cache: Dict[str, Dict[str, Any]] = {}
        self._device_cache_time: Dict[str, float] = {}
        self._device_cache_ttl: float = 10.0  # seconds

        # Smart retry counters (Circuit Breaker):
        # If a gadget is turned off or unplugged (like Classic #2), we don't want to
        # waste 3 whole seconds waiting on it every single turn!
        # If it doesn't answer 3 times in a row, we give it a 60-second break before trying again.
        self._device_failures: Dict[str, int] = {"classic1": 0, "classic2": 0, "webbox": 0, "egauge": 0}
        self._device_next_retry: Dict[str, float] = {"classic1": 0.0, "classic2": 0.0, "webbox": 0.0, "egauge": 0.0}

        # Daily database cleaner timer & disk write batch timer (seconds)
        self._last_prune_time: float = 0.0
        self._last_db_save_time: float = 0.0

        self._pool = ThreadPoolExecutor(max_workers=4)
        self._running = False
        self._poll_thread = None

    def get_live_snapshot(self) -> Dict[str, Any]:
        """
        Grab the newest solar numbers directly from fast RAM memory.
        It's like looking at a sticky note on your desk instead of walking to the filing cabinet!
        """
        if self._latest_snapshot_dict is not None:
            return self._latest_snapshot_dict
        # If memory is empty (right after starting up), check the database filing cabinet
        return self.db.get_latest_snapshot() or {}

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
        if self.egauge:
            self.egauge.close()
        self.db.close()
        self._pool.shutdown(wait=False)

    def poll_once(self) -> TelemetrySnapshot:
        now = time.time()

        # Should we poll each controller?
        # If a controller is unplugged or offline, we give it a 60-second resting break
        # instead of waiting 3 whole seconds for it on every single turn!
        can_poll_c1 = bool(self.classic and (now >= self._device_next_retry.get("classic1", 0.0)))
        can_poll_c2 = bool(self.classic2 and (now >= self._device_next_retry.get("classic2", 0.0)))
        can_poll_wb = bool(self.webbox and (now >= self._device_next_retry.get("webbox", 0.0)))
        can_poll_eg = bool(self.egauge and (now >= self._device_next_retry.get("egauge", 0.0)))

        # Poll active controllers concurrently using worker threads
        fut_c1 = self._pool.submit(self.classic.poll) if can_poll_c1 else None
        fut_c2 = self._pool.submit(self.classic2.poll) if can_poll_c2 else None
        fut_wb = self._pool.submit(self.webbox.poll) if can_poll_wb else None
        fut_eg = self._pool.submit(self.egauge.poll) if can_poll_eg else None

        classic1_data = fut_c1.result() if fut_c1 else (self._latest_classic_full or {})
        classic2_data = fut_c2.result() if fut_c2 else (self._latest_classic2_full or {})
        webbox_data = fut_wb.result() if fut_wb else (self._latest_webbox_full or {})
        egauge_data = fut_eg.result() if fut_eg else (self._latest_egauge_full or {})

        # Check who answered and who is sleeping:
        def update_retry_state(dev_key: str, data: Dict[str, Any]):
            if data.get("online"):
                # Hurray, the device answered! Reset failure counter to zero.
                self._device_failures[dev_key] = 0
                self._device_next_retry[dev_key] = 0.0
            else:
                # It didn't answer. Increment the strike counter.
                fails = self._device_failures.get(dev_key, 0) + 1
                self._device_failures[dev_key] = fails
                # After 3 strikes, tell the monitor to pause trying for 60 seconds.
                if fails >= 3:
                    self._device_next_retry[dev_key] = time.time() + 60.0

        if can_poll_c1:
            update_retry_state("classic1", classic1_data)
        if can_poll_c2:
            update_retry_state("classic2", classic2_data)
        if can_poll_wb:
            update_retry_state("webbox", webbox_data)
        if can_poll_eg:
            update_retry_state("egauge", egauge_data)

        self._latest_classic_full = classic1_data
        self._latest_classic2_full = classic2_data
        self._latest_webbox_full = webbox_data
        self._latest_egauge_full = egauge_data

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

        # eGauge Sub-Metering Telemetry (CT S1: Main House Load, CT S3: Shop Feeder)
        eg_online = bool(egauge_data.get("online"))
        s1_house_watts = float(egauge_data.get("s1_house_load_watts", 0.0))
        s3_feeder_watts = float(egauge_data.get("s3_shop_load_watts", 0.0))
        eg_freq = float(egauge_data.get("frequency_hz", 60.0))

        # ======================================================================
        # The Farm Loads Formula: ((SB4000 Pac) - S3) + S1
        # ======================================================================
        # Imagine electricity like water flowing through pipes across the farm:
        # 1. In the Shop, the Sunny Boy inverter (SB4000) acts like a water fountain,
        #    pumping fresh AC solar electricity into the shop's pipes.
        # 2. CT S3 is a water flow meter sitting on the pipe leaving the Shop and
        #    heading towards the Main House.
        # 3. If tools in the shop are using power, the net power used by the Shop is:
        #    Shop Load = |(Sunny Boy Solar Power) - (Power flowing on S3)|!
        #    We always use the absolute value (positive number) because electrical
        #    loads drink power!
        # 4. In the Main House, CT S1 is a flow meter measuring all the electricity
        #    entering the house (refrigerators, lights, TVs, fans).
        # 5. So the Total Farm Load is: (Net Shop Load) + (Main House S1 Load)!
        #    Formula: abs(pv_ac - s3_feeder_watts) + s1_house_watts
        # ======================================================================
        use_farm_formula = hasattr(self.config, "egauge") and getattr(self.config.egauge, "use_for_farm_loads", True)
        use_s1_only = hasattr(self.config, "egauge") and getattr(self.config.egauge, "use_s1_for_house_loads", True)

        if eg_online and use_farm_formula:
            calc_shop_load = round(abs(pv_ac - s3_feeder_watts), 1)
            active_farm_load = round(calc_shop_load + s1_house_watts, 1)
            active_load_power = active_farm_load
            load_source = "eGauge Farm Load"
        elif eg_online and use_s1_only:
            calc_shop_load = s3_feeder_watts
            active_farm_load = s1_house_watts
            active_load_power = active_farm_load
            load_source = "eGauge S1"
        else:
            calc_shop_load = s3_feeder_watts
            active_load_power = float(si_data.get("load_power_watts", 0.0))
            load_source = "Sunny Island"

        active_freq = eg_freq if (eg_online and eg_freq > 0) else float(si_data.get("ac_frequency", 60.0))

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
            pv_dc_volts=float(classic1_data.get("pv_voltage", 0.0)) or float(classic2_data.get("pv_voltage", 0.0)),
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
            battery_temp_f=float(si_data.get("battery_temp_f", round(float(si_data.get("battery_temp_c", 25.0)) * 1.8 + 32.0, 1))),

            load_power_watts=active_load_power,
            grid_gen_power_watts=float(si_data.get("grid_gen_power_watts", 0.0)),
            generator_volts=float(si_data.get("generator_voltage", 0.0)),
            generator_amps=float(si_data.get("generator_current", 0.0)),
            generator_frequency=float(si_data.get("generator_frequency", 0.0)),
            ac_frequency_hz=active_freq,
            ac_voltage_volts=float(si_data.get("ac_voltage", 120.0)),

            egauge_online=eg_online,
            house_load_watts=s1_house_watts,
            shop_load_watts=calc_shop_load,
            load_source=load_source,

            classic_online=bool(classic1_data.get("online") or classic2_data.get("online")),
            webbox_online=bool(webbox_data.get("online")),
            sunnyboy_online=bool(sb_data.get("online") or pv_ac > 0 or (bool(webbox_data.get("online")) and float(sb_data.get("energy_total_kwh", 0.0)) > 0))
        )

        # 1. Keep this brand-new reading right in fast RAM memory!
        # Every 3 seconds, browsers asking for "/api/live" get this fresh data in < 1 millisecond!
        self._latest_snapshot = snapshot
        self._latest_snapshot_dict = snapshot.model_dump()

        # 2. Save to the SQLite notebook on the disk for history charts:
        # We write immediately on the very first poll, and then once every `db_save_interval_seconds`
        # (15 seconds) so we don't wear out the disk with constant writes while still keeping
        # live screen updates super fast (every 3 seconds)!
        db_save_interval = getattr(self.config.storage, "db_save_interval_seconds", 15)
        if self._last_db_save_time == 0.0 or (time.time() - self._last_db_save_time >= db_save_interval):
            self.db.save_snapshot(snapshot)
            self._last_db_save_time = time.time()

        # 3. Publish to MQTT for Home Assistant (reusing our already-built dictionary!)
        if self.mqtt:
            self.mqtt.publish_snapshot(snapshot, payload=self._latest_snapshot_dict)

        return snapshot

    def get_device_telemetry(self, device_id: str) -> Dict[str, Any]:
        """Fetch rich real-time telemetry for a specific device."""
        dev = device_id.lower().strip()
        now = time.time()

        # Check our 10-second sticky note memory first!
        # If someone keeps clicking or refreshing the screen, we give them the cached answer
        # so we don't bombard the solar controllers over the wire.
        cached = self._device_cache.get(dev)
        cached_t = self._device_cache_time.get(dev, 0.0)
        if cached and (now - cached_t < self._device_cache_ttl):
            return cached

        res: Dict[str, Any] = {}

        # Our Friendly Temperature Translator:
        # Electronic chips and sensors often speak in Celsius (°C).
        # But we want all our dashboards to speak in friendly Fahrenheit (°F)!
        # The magic recipe to turn Celsius into Fahrenheit is: (Celsius * 1.8) + 32.
        # This little helper checks every channel and translates any °C into °F!
        def _convert_channels_to_f(channels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            converted = []
            for ch in channels:
                c = dict(ch)
                unit = c.get("unit", "")
                meta = c.get("meta", "")
                if (unit in ("°C", "degC", "C") or meta in ("BatTmp", "Temperature")) and unit != "°F":
                    try:
                        val_c = float(str(c.get("value", "")).replace(",", ""))
                        val_f = round(val_c * 1.8 + 32.0, 1)
                        c["value"] = f"{val_f:.1f}"
                        c["unit"] = "°F"
                    except (ValueError, TypeError):
                        pass
                converted.append(c)
            return converted

        if dev in ("midnite", "classic", "classic-1", "midnite-1", "classic1", "midnite1"):
            # Only ask for a full scan if Classic #1 is healthy and not in a failure cooldown
            if self.classic and self._device_failures.get("classic1", 0) < 3:
                try:
                    full = self.classic.poll_full()
                    if full.get("online"):
                        full["device_id"] = "classic-1"
                        full["device_name"] = "MidNite Solar Classic #1"
                        self._device_cache[dev] = full
                        self._device_cache_time[dev] = now
                        return full
                except Exception as e:
                    logger.debug(f"Live poll_full for MidNite #1 failed: {e}")
            
            c = self._latest_classic_full
            res = {
                "device_id": "classic-1",
                "device_name": "MidNite Solar Classic #1",
                "model": "Classic MPPT Charge Controller (192.168.42.129)",
                "online": bool(c.get("online")),
                "data": c,
                "registers": []
            }

        elif dev in ("classic-2", "midnite-2", "classic2", "midnite2"):
            # If Classic #2 is offline, don't freeze the web browser for 3 seconds!
            # Return our offline status note immediately.
            if self.classic2 and self._device_failures.get("classic2", 0) < 3:
                try:
                    full = self.classic2.poll_full()
                    if full.get("online"):
                        full["device_id"] = "classic-2"
                        full["device_name"] = "MidNite Solar Classic #2"
                        self._device_cache[dev] = full
                        self._device_cache_time[dev] = now
                        return full
                except Exception as e:
                    logger.debug(f"Live poll_full for MidNite #2 failed: {e}")

            c2 = self._latest_classic2_full
            res = {
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
            raw_channels = _convert_channels_to_f([c for c in si.get("raw_channels", []) if c.get("meta") in lynk_metas])
            
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
                    {"meta": "BatTmp", "name": "Battery cell temperature", "value": f"{bat_tmp_f:.1f}", "unit": "°F"},
                    {"meta": "Soh", "name": "Current battery capacity (SoH)", "value": f"{bat_soh:.0f}", "unit": "%"},
                    {"meta": "BatChrgVtg", "name": "BMS dynamic target charge voltage", "value": "54.40", "unit": "V"},
                    {"meta": "BatChrgCurMax", "name": "BMS max charge current limit", "value": "130.0", "unit": "A"},
                    {"meta": "BatDiChgCurMax", "name": "BMS max discharge current limit", "value": "130.0", "unit": "A"},
                    {"meta": "BatDiChgVtgMin", "name": "Low battery cut-off threshold", "value": "48.00", "unit": "V"},
                    {"meta": "BatCpyNom", "name": "Installed battery bank capacity", "value": "130", "unit": "Ah"},
                    {"meta": "BatTyp", "name": "Inverter battery configuration", "value": "LiIon_Ext-BMS", "unit": ""},
                    {"meta": "CAN:0x351", "name": "Dynamic Charge / Discharge Limits", "value": "Active", "unit": "Target 54.4V"},
                    {"meta": "CAN:0x355", "name": "BMS State of Charge & Health", "value": f"{bat_soc:.0f}% / {bat_soh:.0f}%", "unit": "CAN Frame"},
                    {"meta": "CAN:0x356", "name": "BMS Terminal Voltage, Current & Temp", "value": f"{bat_vtg:.1f}V | {bat_cur:+.1f}A | {bat_tmp_f:.1f}°F", "unit": "CAN Frame"},
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

            res = {
                "device_id": "battery",
                "device_name": "Discover AES Lithium Battery & LYNK II",
                "model": "Discover AES LiFePO4 (LYNK II Closed-Loop)",
                "online": bool(si.get("online")),
                "data": battery_data,
                "channels": raw_channels
            }

        elif dev in ("sunny-island", "si", "generator", "gen"):
            si = self._latest_webbox_full.get("sunny_island", {})
            if not si or not si.get("load_power_watts"):
                snap = self.db.get_latest_snapshot()
                if snap:
                    si = {
                        "online": bool(snap.get("webbox_online")),
                        "inverter_power_watts": snap.get("load_power_watts", 0.0),
                        "load_power_watts": snap.get("load_power_watts", 0.0),
                        "grid_gen_power_watts": snap.get("grid_gen_power_watts", 0.0),
                        "generator_voltage": snap.get("generator_volts", 0.0),
                        "generator_current": snap.get("generator_amps", 0.0),
                        "generator_frequency": snap.get("generator_frequency", 0.0),
                        "ac_voltage": snap.get("ac_voltage_volts", 120.0),
                        "ac_frequency": snap.get("ac_frequency_hz", 60.0),
                        "raw_channels": []
                    }
            
            raw_ch = _convert_channels_to_f(list(si.get("raw_channels", [])))
            # Include eGauge sub-meter readings as companion diagnostic channels if online
            if self._latest_egauge_full and self._latest_egauge_full.get("online"):
                eg = self._latest_egauge_full
                raw_ch.insert(0, {
                    "meta": "eGauge:S1",
                    "name": "Main House Load (eGauge CT S1)",
                    "value": f"{eg.get('s1_house_load_watts', 0.0):.1f}",
                    "unit": "W"
                })
                raw_ch.insert(1, {
                    "meta": "eGauge:S3",
                    "name": "Shop Load & SB4000 (eGauge CT S3)",
                    "value": f"{eg.get('s3_shop_load_watts', 0.0):.1f}",
                    "unit": "W"
                })

            res = {
                "device_id": "sunny-island",
                "device_name": "SMA Sunny Island 6048 & Household Loads",
                "model": "Sunny Island 6048-US Inverter/Charger",
                "online": bool(si.get("online")),
                "data": si,
                "channels": raw_ch
            }

        elif dev in ("sunny-boy", "sb"):
            sb = self._latest_webbox_full.get("sunny_boy", {})
            if not sb:
                snap = self._latest_snapshot_dict or self.db.get_latest_snapshot()
                if snap:
                    sb = {
                        "online": bool(snap.get("sunnyboy_online")),
                        "pv_power_watts": snap.get("pv_ac_power_watts", 0.0),
                        "energy_total_kwh": snap.get("pv_ac_total_kwh", 0.0),
                        "raw_channels": []
                    }
            res = {
                "device_id": "sunny-boy",
                "device_name": "SMA Sunny Boy 4000",
                "model": "Sunny Boy 4000-US Grid-Tie Inverter",
                "online": bool(sb.get("online")),
                "data": sb,
                "channels": _convert_channels_to_f(list(sb.get("raw_channels", [])))
            }

        elif dev in ("egauge", "eg3010", "meter", "submeter", "households", "household", "loads", "load", "main-house", "house-load", "shop-load", "farm", "farm-load", "farm-loads"):
            eg = dict(self._latest_egauge_full) if self._latest_egauge_full else {}
            if not eg or not eg.get("online"):
                if self.egauge:
                    try:
                        eg = self.egauge.poll_full()
                    except Exception as err:
                        logger.debug(f"Direct eGauge poll encountered error: {err}")
            if not eg:
                snap = self.db.get_latest_snapshot()
                eg = {
                    "online": bool(snap.get("egauge_online") if snap else False),
                    "s1_house_load_watts": snap.get("house_load_watts", 0.0) if snap else 0.0,
                    "s3_shop_load_watts": snap.get("shop_load_watts", 0.0) if snap else 0.0,
                    "frequency_hz": snap.get("ac_frequency_hz", 60.0) if snap else 60.0,
                    "voltage_volts": 120.0,
                    "raw_registers": []
                }

            # Augment with Farm Loads calculation: ((SB4000 Pac) - S3) + S1
            sb_pwr = float(self._latest_webbox_full.get("sunny_boy", {}).get("pv_power_watts", 0.0))
            s1_pwr = float(eg.get("s1_house_load_watts", 0.0))
            s3_pwr = float(eg.get("s3_shop_load_watts", 0.0))
            calc_shop = round(abs(sb_pwr - s3_pwr), 1)
            calc_farm = round(calc_shop + s1_pwr, 1)

            eg["sb4000_pac_watts"] = sb_pwr
            eg["calculated_shop_load_watts"] = calc_shop
            eg["farm_load_watts"] = calc_farm

            channels = list(eg.get("channels") or eg.get("raw_registers") or [])
            channels.insert(0, {
                "meta": "calc:farm_load",
                "name": "Total Farm Load ((SB4000 Pac - S3) + S1)",
                "value": f"{calc_farm:.1f}",
                "unit": "W"
            })
            channels.insert(1, {
                "meta": "calc:shop_load",
                "name": "Shop Load (|SB4000 Pac - S3|)",
                "value": f"{calc_shop:.1f}",
                "unit": "W"
            })

            res = {
                "device_id": "egauge",
                "device_name": "eGauge EG3010 Energy Meter & Farm Loads",
                "model": "eGauge EG3010 Multi-Channel Sub-Meter (120V S1 House + S3 Shop)",
                "online": bool(eg.get("online")),
                "data": eg,
                "channels": channels
            }
        else:
            return {"error": f"Unknown device ID: {device_id}"}

        # Save this result in our 10-second sticky note memory before returning!
        self._device_cache[dev] = res
        self._device_cache_time[dev] = now
        return res

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

                # Database Librarian:
                # Once every 24 hours (86,400 seconds), we keep a full 1 year (365 days) of
                # 15-second snapshots, and neatly roll up anything older than 1 year into
                # 10-minute average rows so we keep our farm's history forever!
                now = time.time()
                if now - self._last_prune_time > 86400:
                    self._last_prune_time = now
                    try:
                        rollup_mins = getattr(self.config.storage, "rollup_interval_minutes", 10)
                        compacted = self.db.rollup_old_snapshots(
                            retention_days=self.config.storage.retention_days,
                            rollup_minutes=rollup_mins
                        )
                        if compacted > 0:
                            logger.info(
                                f"Database librarian: Compacted {compacted} rows older than "
                                f"{self.config.storage.retention_days} days into {rollup_mins}-minute averages."
                            )
                    except Exception as err:
                        logger.warning(f"Database rollup task had a hiccup: {err}")

            except Exception as e:
                logger.error(f"Error during polling cycle: {e}", exc_info=True)

            elapsed = time.time() - start_t
            sleep_time = max(0.2, interval - elapsed)
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
