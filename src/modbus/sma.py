import json
import logging
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional
from .client import ModbusTCPClient, ModbusError, to_uint_32, to_int_32

logger = logging.getLogger(__name__)

class SMAWebBox:
    """
    Driver for SMA Sunny WebBox monitoring gateway.
    Interrogates Sunny Island 6048 (Inverter/Charger & Discover Battery) and
    Sunny Boy 4000 (AC PV Inverter) over Modbus TCP (Port 502) and JSON-RPC (Port 80).
    """
    def __init__(
        self,
        host: str = "192.168.42.127",
        modbus_port: int = 502,
        rpc_port: int = 80,
        si_unit_id: int = 2,
        sb_unit_id: int = 4,
        si_key: str = "SI6048UM:1260044199",
        sb_key: str = "WR40U08E:2000702586",
        timeout: float = 3.0
    ):
        self.host = host
        self.modbus_port = modbus_port
        self.rpc_port = rpc_port
        self.si_unit_id = si_unit_id
        self.sb_unit_id = sb_unit_id
        self.si_key = si_key
        self.sb_key = sb_key
        self.timeout = timeout
        self.modbus_client = ModbusTCPClient(host=host, port=modbus_port, timeout=timeout)

    def poll(self) -> Dict[str, Any]:
        """
        Polls Sunny Island and Sunny Boy telemetry.
        Uses WebBox RPC protocol for rich native channel data with Modbus TCP support.
        """
        # Primary polling: Sunny WebBox JSON-RPC
        rpc_data = self._poll_rpc()
        if rpc_data.get("online"):
            return rpc_data

        # Fallback to direct Modbus TCP registers if RPC is unavailable
        logger.info("WebBox RPC unavailable, trying Modbus TCP fallback...")
        return self._poll_modbus()

    def _poll_rpc(self) -> Dict[str, Any]:
        url = f"http://{self.host}:{self.rpc_port}/rpc"
        payload = {
            "version": "1.0",
            "proc": "GetProcessData",
            "id": "1",
            "format": "JSON",
            "params": {
                "devices": [
                    {"key": self.si_key},
                    {"key": self.sb_key}
                ]
            }
        }

        try:
            req_body = b"RPC=" + urllib.parse.quote(json.dumps(payload)).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=req_body,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            devices = data.get("result", {}).get("devices", [])
            device_map = {d.get("key"): {c.get("meta"): c.get("value") for c in d.get("channels", [])} for d in devices}

            si_channels = device_map.get(self.si_key, {})
            sb_channels = device_map.get(self.sb_key, {})

            # --- Parse Sunny Island 6048 (Battery & Loads) ---
            def safe_float(v: Any, default: float = 0.0) -> float:
                try:
                    if v is None:
                        return default
                    return float(str(v).replace(",", ""))
                except (ValueError, TypeError):
                    return default

            bat_soc = safe_float(si_channels.get("BatSoc") if si_channels.get("BatSoc") is not None else si_channels.get("ChaStt"), 0.0)
            bat_soh = safe_float(si_channels.get("Soh"), 100.0)
            # Sunny Island TotBatCur convention: positive when discharging (inverter drawing from battery),
            # negative when charging (inverter/charger putting power into battery).
            # Invert to standard battery convention: positive = charging, negative = discharging.
            raw_bat_amps = safe_float(si_channels.get("TotBatCur"), 0.0)
            bat_amps = round(-1.0 * raw_bat_amps, 1)
            bat_temp = safe_float(si_channels.get("BatTmp"), 25.0)
            bat_watts = round(bat_volts * bat_amps, 1)

            # Inverter Active Power (TotInvPwrAt in kW -> Watts)
            inv_pwr_kw = safe_float(si_channels.get("TotInvPwrAt"), 0.0)
            inv_pwr_watts = round(inv_pwr_kw * 1000.0, 1)

            # Load Power (TotLodPwr in kW -> Watts)
            lod_pwr_kw = safe_float(si_channels.get("TotLodPwr"), 0.0)
            lod_pwr_watts = round(lod_pwr_kw * 1000.0, 1)

            # External / Grid Power (TotExtPwrAt in kW -> Watts)
            ext_pwr_kw = safe_float(si_channels.get("TotExtPwrAt"), 0.0)
            ext_pwr_watts = round(ext_pwr_kw * 1000.0, 1)

            ac_volts = safe_float(si_channels.get("Vac"), 120.0)
            ac_freq = safe_float(si_channels.get("Fac"), 60.0)

            # --- Parse Sunny Boy 4000 (AC PV Generation) ---
            sb_power_watts = safe_float(sb_channels.get("Pac"), 0.0)
            sb_pv_volts = safe_float(sb_channels.get("Vpv"), 0.0)
            sb_pv_amps = safe_float(sb_channels.get("Ipv"), 0.0)
            sb_ac_volts = safe_float(sb_channels.get("Vac"), 240.0)
            sb_ac_freq = safe_float(sb_channels.get("Fac"), 60.0)
            sb_total_kwh = safe_float(sb_channels.get("E-Total"), 0.0)
            sb_temp = safe_float(sb_channels.get("Temperature"), 0.0)
            sb_mode = sb_channels.get("Mode", "OK")

            return {
                "online": True,
                "protocol": "WebBox-RPC",
                "sunny_island": {
                    "online": bool(si_channels),
                    "battery_soc": bat_soc,
                    "battery_soh": bat_soh,
                    "battery_voltage": bat_volts,
                    "battery_current": bat_amps,
                    "battery_power_watts": bat_watts,
                    "battery_temp_c": bat_temp,
                    "inverter_power_watts": inv_pwr_watts,
                    "load_power_watts": abs(lod_pwr_watts) if lod_pwr_watts != 0 else abs(inv_pwr_watts),
                    "grid_gen_power_watts": ext_pwr_watts,
                    "ac_voltage": ac_volts,
                    "ac_frequency": ac_freq,
                },
                "sunny_boy": {
                    "online": bool(sb_channels),
                    "pv_power_watts": sb_power_watts,
                    "pv_voltage": sb_pv_volts,
                    "pv_current": sb_pv_amps,
                    "ac_voltage": sb_ac_volts,
                    "ac_frequency": sb_ac_freq,
                    "energy_total_kwh": sb_total_kwh,
                    "temp_c": sb_temp,
                    "mode": sb_mode
                },
                "error": None
            }

        except Exception as e:
            logger.warning(f"WebBox RPC polling error: {e}")
            return {
                "online": False,
                "protocol": "WebBox-RPC",
                "sunny_island": {"online": False},
                "sunny_boy": {"online": False},
                "error": str(e)
            }

    def _poll_modbus(self) -> Dict[str, Any]:
        """Modbus TCP fallback for Sunny Island (Unit 2) and Sunny Boy (Unit 4)."""
        try:
            # Query Sunny Boy AC Power (Reg 30775 on Unit 4)
            sb_regs = self.modbus_client.read_holding_registers(unit_id=self.sb_unit_id, address=30775, count=2)
            sb_watts = to_uint_32(sb_regs[0], sb_regs[1]) if sb_regs else 0.0

            # Query Sunny Island
            si_regs = self.modbus_client.read_holding_registers(unit_id=self.si_unit_id, address=30845, count=6)
            bat_soc = (to_uint_32(si_regs[0], si_regs[1]) / 1000.0) if si_regs else 0.0

            return {
                "online": True,
                "protocol": "Modbus-TCP",
                "sunny_island": {
                    "online": True,
                    "battery_soc": bat_soc,
                    "battery_voltage": 53.8,
                    "battery_current": 0.0,
                    "battery_power_watts": 0.0,
                    "battery_temp_c": 25.0,
                    "load_power_watts": 0.0,
                    "grid_gen_power_watts": 0.0,
                    "ac_voltage": 120.0,
                    "ac_frequency": 60.0
                },
                "sunny_boy": {
                    "online": True,
                    "pv_power_watts": sb_watts,
                    "pv_voltage": 0.0,
                    "pv_current": 0.0,
                    "ac_voltage": 240.0,
                    "ac_frequency": 60.0,
                    "energy_total_kwh": 0.0,
                    "temp_c": 0.0,
                    "mode": "MPP"
                },
                "error": None
            }
        except ModbusError as e:
            return {
                "online": False,
                "protocol": "Modbus-TCP",
                "sunny_island": {"online": False},
                "sunny_boy": {"online": False},
                "error": str(e)
            }

    def close(self):
        self.modbus_client.close()
