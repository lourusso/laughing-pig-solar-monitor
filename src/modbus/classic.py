from __future__ import annotations
import logging
import time
from typing import Dict, Any, Optional, List
from .client import ModbusTCPClient, ModbusError, to_signed_16, to_uint_32

logger = logging.getLogger(__name__)

# ==============================================================================
# Solar Charging Stages: How to Fill an Electric Tank!
# ==============================================================================
# Think of charging our big lithium battery like filling a water jug:
# - BULK_MPPT: The jug is thirsty! We open the solar faucet wide open and pour in
#   as much sunshine as the panels can harvest!
# - ABSORB: The jug is almost full (around 85-95%). We slow down the water flow
#   so it doesn't splash or overfill, gently topping it up to the brim.
# - FLOAT: The jug is 100% full! We only trickle in tiny sips to keep it full
#   while supplying whatever power the house needs.
# - RESTING: The sun has set for the night! There are no solar rays, so the
#   controller takes a cozy nap until the morning sun peeks over the horizon.
# ==============================================================================
STAGE_MAP = {
    0: "RESTING",
    3: "ABSORB",
    4: "BULK_MPPT",
    5: "FLOAT",
    6: "FLOAT_MPPT",
    7: "EQUALIZE",
    10: "HYPER_VOC",
    18: "EQ_MPPT",
}

# ==============================================================================
# MidNite Solar Classic: The Solar Power Wizard!
# ==============================================================================
# What does a MidNite Classic do?
# Solar panels on the roof create high voltage electricity (like 80 to 120 Volts).
# But our battery bank only wants about 52 Volts!
# The MidNite Classic is an MPPT controller ("Maximum Power Point Tracker").
# It acts like a high-tech electric transformer and wizard:
# It constantly hunts for the perfect sweet spot of sunlight and converts
# high-voltage solar rays into high-current, safe power for our battery!
# ==============================================================================
class MidNiteClassic:
    """
    Driver for MidNite Solar Classic MPPT Charge Controller via Modbus TCP.
    Reads real-time PV generation, battery charging stage, and temperatures.
    """
    def __init__(self, host: str = "192.168.42.129", port: int = 502, unit_id: int = 1, timeout: float = 3.0):
        # House number (IP address) on our farm network, and port 502 (Modbus front door)
        self.client = ModbusTCPClient(host=host, port=port, timeout=timeout)
        self.unit_id = unit_id
        self.host = host
        # Permanent memory for factory info that never changes (model, MAC address, build date)
        self._unit_info_cache: Optional[Dict[str, Any]] = None
        # 60-second memory for charge setpoints that rarely change
        self._cfg_cache: Optional[Dict[str, Any]] = None
        self._cfg_cache_time: float = 0.0

    @staticmethod
    def _fmt_time(sec: int) -> str:
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        if h > 0:
            return f"{h}h {m}m {s}s"
        if m > 0:
            return f"{m}m {s}s"
        return f"{s}s"

    def poll(self) -> Dict[str, Any]:
        """
        Poll the Classic and return parsed telemetry.
        We ask the Classic to open its memory drawer (registers 4115 to 4144)
        and read out all 30 registers in one single trip!
        """
        try:
            # Read block from register 4115 to 4144 (30 registers) in one single packet!
            # Modbus 0-based address for register 4115 is 4114
            regs = self.client.read_holding_registers(unit_id=self.unit_id, address=4114, count=30)

            # In the Classic's memory drawer, voltages and currents are multiplied by 10
            # to save decimal points (for example, 52.4 Volts is saved as 524).
            # Dividing by 10.0 gives us the real decimal number!
            bat_voltage = regs[0] / 10.0           # 4115: dispavgVbatt (V)
            pv_voltage = regs[1] / 10.0            # 4116: dispavgVpv (V)
            bat_current = to_signed_16(regs[2]) / 10.0  # 4117: IbattDisplayS (A)
            energy_today = regs[3] / 10.0          # 4118: kW-Hours (kWh)
            power_watts = float(regs[4])           # 4119: Watts
            
            # 4120: ComboChargeStage (High byte = stage, Low byte = state)
            combo_stage = regs[5]
            stage_code = (combo_stage >> 8) & 0xFF
            stage_str = STAGE_MAP.get(stage_code, f"STAGE_{stage_code}")

            pv_current = regs[6] / 10.0            # 4121: PvInputCurrent (A)
            voc_volts = regs[7] / 10.0             # 4122: VocLastMeasured (V)
            pv_highest_v = regs[8] / 10.0 if len(regs) > 8 else 0.0  # 4123: HighestVinputLog (V)
            amphours_today = regs[10] if len(regs) > 10 else 0       # 4125: AmpHours
            
            # 4126 & 4127: Lifetime Energy Total (kWh)
            # Reg 4126 is low word, 4127 is high word
            lifetime_low = regs[11]
            lifetime_high = regs[12]
            total_kwh = ((lifetime_high << 16) + lifetime_low) / 10.0

            lifetime_amphours = ((regs[14] << 16) + regs[13]) if len(regs) > 14 else 0

            # 4132: Battery temperature, 4133: FET temp, 4134: PCB temp
            # These are measured in Celsius, then converted to friendly Fahrenheit!
            bat_temp = to_signed_16(regs[17]) / 10.0 if len(regs) > 17 else 25.0
            fet_temp = to_signed_16(regs[18]) / 10.0 if len(regs) > 18 else 25.0
            pcb_temp = to_signed_16(regs[19]) / 10.0 if len(regs) > 19 else 25.0

            night_minutes = regs[20] if len(regs) > 20 else 0
            float_sec = regs[23] if len(regs) > 23 else 0
            absorb_sec = regs[24] if len(regs) > 24 else 0
            pwm_duty = regs[26] if len(regs) > 26 else 0
            reset_reason = regs[27] if len(regs) > 27 else 0
            equalize_sec = regs[28] if len(regs) > 28 else 0

            return {
                "online": True,
                "pv_power_watts": power_watts,
                "pv_voltage": pv_voltage,
                "pv_current": pv_current,
                "pv_voc": voc_volts,
                "pv_highest_v": pv_highest_v,
                "battery_voltage": bat_voltage,
                "battery_current": bat_current,
                "energy_today_kwh": energy_today,
                "energy_total_kwh": total_kwh,
                "amphours_today": amphours_today,
                "lifetime_amphours": lifetime_amphours,
                "charge_stage": stage_str,
                "pcb_temp_c": pcb_temp,
                "fet_temp_c": fet_temp,
                "battery_temp_c": bat_temp,
                "pcb_temp_f": round(pcb_temp * 1.8 + 32.0, 1),
                "fet_temp_f": round(fet_temp * 1.8 + 32.0, 1),
                "battery_temp_f": round(bat_temp * 1.8 + 32.0, 1),
                "night_minutes": night_minutes,
                "float_time_today_sec": float_sec,
                "float_time_today_str": self._fmt_time(float_sec),
                "absorb_time_sec": absorb_sec,
                "absorb_time_str": self._fmt_time(absorb_sec),
                "pwm_duty": pwm_duty,
                "reset_reason": reset_reason,
                "equalize_time_sec": equalize_sec,
                "equalize_time_str": self._fmt_time(equalize_sec),
                "error": None
            }

        except ModbusError as e:
            logger.warning(f"MidNite Classic poll error: {e}")
            return {
                "online": False,
                "pv_power_watts": 0.0,
                "pv_voltage": 0.0,
                "pv_current": 0.0,
                "battery_voltage": 0.0,
                "battery_current": 0.0,
                "energy_today_kwh": 0.0,
                "charge_stage": "OFFLINE",
                "error": str(e)
            }

    def poll_full(self) -> Dict[str, Any]:
        """Poll the Classic for all available real-time, diagnostic, and configuration data."""
        base_data = self.poll()
        if not base_data.get("online"):
            return {
                "device_id": "midnite",
                "device_name": "MidNite Solar Classic",
                "model": "Classic MPPT Charge Controller",
                "online": False,
                "error": base_data.get("error"),
                "data": base_data,
                "registers": []
            }

        data = dict(base_data)
        registers = []
        fmt_time = self._fmt_time

        # 1. Reuse the 30 registers (4115 - 4144) already fetched in `self.poll()`!
        # No need to bother the Classic a second time for the exact same drawer!
        reg_defs_main = [
            (4115, "dispavgVbatt", "Average Battery Voltage", f"{data['battery_voltage']} V"),
            (4116, "dispavgVpv", "Average PV Input Voltage", f"{data['pv_voltage']} V"),
            (4117, "IbattDisplayS", "Average Battery Current", f"{data['battery_current']} A"),
            (4118, "kW-Hours", "Daily Solar Energy Yield", f"{data['energy_today_kwh']} kWh"),
            (4119, "Watts", "Instantaneous Power", f"{data['pv_power_watts']} W"),
            (4120, "ComboChargeStage", "Active Charge Stage", data['charge_stage']),
            (4121, "PvInputCurrent", "Average PV Input Current", f"{data['pv_current']} A"),
            (4122, "VocLastMeasured", "Last Measured Voc", f"{data['pv_voc']} V"),
            (4123, "HighestVinputLog", "Highest PV Input Voltage", f"{data.get('pv_highest_v', 0.0)} V"),
            (4125, "AmpHours", "Daily Amp-Hours", f"{data.get('amphours_today', 0)} Ah"),
            (4126, "Lifetime kW-Hours", "Lifetime Energy Generation", f"{data['energy_total_kwh']} kWh"),
            (4128, "LifetimeAmpHours", "Lifetime Amp-Hours", f"{data.get('lifetime_amphours', 0)} Ah"),
            (4132, "BATTtemperature", "Battery Temp Sensor", f"{data.get('battery_temp_f', round(data['battery_temp_c']*1.8+32, 1)):.1f} °F"),
            (4133, "FETtemperature", "Power FET Temperature", f"{data.get('fet_temp_f', round(data['fet_temp_c']*1.8+32, 1)):.1f} °F"),
            (4134, "PCBTemperature", "PCB Control Board Temp", f"{data.get('pcb_temp_f', round(data['pcb_temp_c']*1.8+32, 1)):.1f} °F"),
            (4135, "NiteMinutesNoPwr", "Night Minutes (No Solar)", f"{data.get('night_minutes', 0)} min"),
            (4138, "FloatTimeToday", "Time in Float Stage Today", data.get('float_time_today_str', '0s')),
            (4139, "AbsorbTime", "Absorb Time Counter", data.get('absorb_time_str', '0s')),
            (4141, "PWM_ReadOnly", "PWM Duty Cycle Command", f"{data.get('pwm_duty', 0)}"),
            (4142, "Reason_For_Reset", "Reset Reason Code", f"{data.get('reset_reason', 0)}"),
            (4143, "Equalize Time", "Equalize Time Remaining", data.get('equalize_time_str', '0s'))
        ]
        for r_num, r_name, r_desc, r_val in reg_defs_main:
            registers.append({"register": r_num, "name": r_name, "description": r_desc, "value": r_val})

        # 2. Unit info & build date (4101 - 4114):
        # Since a controller's MAC address and factory birthday never change, we only
        # read this drawer once and remember it forever in `self._unit_info_cache`!
        if self._unit_info_cache is None:
            try:
                regs_info = self.client.read_holding_registers(unit_id=self.unit_id, address=4100, count=14)
                if len(regs_info) >= 8:
                    pcb_rev = (regs_info[0] >> 8) & 0xFF
                    unit_code = regs_info[0] & 0xFF
                    model_map = {150: "Classic 150", 200: "Classic 200", 250: "Classic 250", 251: "Classic 250-KS"}
                    model_str = model_map.get(unit_code, f"Classic {unit_code}")
                    yr = regs_info[1]
                    mo = (regs_info[2] >> 8) & 0xFF
                    dy = regs_info[2] & 0xFF
                    sw_date = f"{yr:04d}-{mo:02d}-{dy:02d}"
                    mac_bytes = [
                        (regs_info[7] >> 8) & 0xFF, regs_info[7] & 0xFF,
                        (regs_info[6] >> 8) & 0xFF, regs_info[6] & 0xFF,
                        (regs_info[5] >> 8) & 0xFF, regs_info[5] & 0xFF
                    ]
                    mac_address = ":".join(f"{b:02X}" for b in mac_bytes)
                    dev_id = ((regs_info[11] << 16) + regs_info[10]) if len(regs_info) >= 12 else "--"
                    self._unit_info_cache = {
                        "data": {
                            "model_name": model_str,
                            "pcb_rev": pcb_rev,
                            "sw_date": sw_date,
                            "mac_address": mac_address,
                            "device_id": dev_id,
                        },
                        "registers": [
                            {"register": 4101, "name": "UNIT_ID", "description": "Model & PCB Revision", "value": f"{model_str} (PCB Rev {pcb_rev})"},
                            {"register": 4102, "name": "UNIT_SW_DATE", "description": "Firmware Build Date", "value": sw_date},
                            {"register": 4106, "name": "UNIT_MAC_Address", "description": "Ethernet MAC Address", "value": mac_address},
                            {"register": 4111, "name": "UNIT_Device_ID", "description": "Factory Unit Device ID", "value": str(dev_id)}
                        ]
                    }
            except Exception as e:
                logger.debug(f"Could not read unit info registers: {e}")

        if self._unit_info_cache:
            data.update(self._unit_info_cache["data"])
            registers.extend(self._unit_info_cache["registers"])

        # 3 & 4. Configuration Setpoints (4153-4165 & 4244-4250):
        # Charge setpoints rarely change, so we cache them for 60 seconds!
        now = time.time()
        if self._cfg_cache is None or (now - self._cfg_cache_time > 60.0):
            cfg_data: Dict[str, Any] = {}
            cfg_regs: List[Dict[str, Any]] = []
            try:
                regs_cfg = self.client.read_holding_registers(unit_id=self.unit_id, address=4152, count=13)
                if len(regs_cfg) >= 12:
                    cfg_data["absorb_setpoint_sec"] = regs_cfg[1]
                    cfg_data["absorb_setpoint_str"] = fmt_time(regs_cfg[1])
                    cfg_data["max_temp_comp_v"] = regs_cfg[2] / 10.0
                    cfg_data["min_temp_comp_v"] = regs_cfg[3] / 10.0
                    cfg_data["temp_comp_mv_c_cell"] = -(regs_cfg[4] / 10.0)
                    cfg_data["equalize_setpoint_sec"] = regs_cfg[9]
                    cfg_data["equalize_setpoint_str"] = fmt_time(regs_cfg[9])
                    cfg_data["equalize_interval_days"] = regs_cfg[10]
                    mppt_mode_code = regs_cfg[11]
                    mppt_modes = {0: "Solar", 1: "PV U-Set", 2: "Wind Track", 3: "Dynamic", 4: "U-Set 2"}
                    cfg_data["mppt_mode"] = mppt_modes.get(mppt_mode_code, f"Mode {mppt_mode_code}")

                    cfg_regs.extend([
                        {"register": 4154, "name": "Absorb Time Setpoint", "description": "Absorb Duration Setting", "value": cfg_data["absorb_setpoint_str"]},
                        {"register": 4155, "name": "Max Temp Comp Volts", "description": "Maximum Temp-Comp Voltage", "value": f"{cfg_data['max_temp_comp_v']} V"},
                        {"register": 4156, "name": "Min Temp Comp Volts", "description": "Minimum Temp-Comp Voltage", "value": f"{cfg_data['min_temp_comp_v']} V"},
                        {"register": 4157, "name": "Temp Comp Slope", "description": "Battery Temp Compensation", "value": f"{cfg_data['temp_comp_mv_c_cell'] / 1.8:.2f} mV/°F/cell"},
                        {"register": 4162, "name": "Equalize Time Setpoint", "description": "Equalize Duration Setting", "value": cfg_data["equalize_setpoint_str"]},
                        {"register": 4163, "name": "Equalize Interval", "description": "Auto-Equalize Interval", "value": f"{cfg_data['equalize_interval_days']} Days"},
                        {"register": 4164, "name": "MPPT Mode", "description": "Tracking Algorithm Mode", "value": cfg_data["mppt_mode"]}
                    ])
            except Exception as e:
                logger.debug(f"Could not read setpoint registers 4153-4165: {e}")

            try:
                regs_reg = self.client.read_holding_registers(unit_id=self.unit_id, address=4243, count=7)
                if len(regs_reg) >= 6:
                    cfg_data["temp_comp_target_v"] = regs_reg[0] / 10.0
                    cfg_data["nominal_bat_v"] = regs_reg[1]
                    cfg_data["ending_amps"] = regs_reg[2] / 10.0
                    cfg_data["rebulk_v"] = regs_reg[5] / 10.0

                    cfg_regs.extend([
                        {"register": 4244, "name": "VbattRegSetPTmpComp", "description": "Temp-Compensated Regulation Target", "value": f"{cfg_data['temp_comp_target_v']} V"},
                        {"register": 4245, "name": "VbattNominal", "description": "Nominal Battery Bank Voltage", "value": f"{cfg_data['nominal_bat_v']} V"},
                        {"register": 4246, "name": "EndingAmps", "description": "Absorb Ending Current", "value": f"{cfg_data['ending_amps']} A"},
                        {"register": 4249, "name": "RebulkVolts", "description": "Rebulk Trigger Voltage", "value": f"{cfg_data['rebulk_v']} V"}
                    ])
            except Exception as e:
                logger.debug(f"Could not read regulation registers 4244-4250: {e}")

            if cfg_data:
                self._cfg_cache = {"data": cfg_data, "registers": cfg_regs}
                self._cfg_cache_time = now

        if self._cfg_cache:
            data.update(self._cfg_cache["data"])
            registers.extend(self._cfg_cache["registers"])

        # Calculate Fahrenheit temperatures
        for t_key in ["battery_temp_c", "fet_temp_c", "pcb_temp_c"]:
            if t_key in data:
                data[t_key.replace("_c", "_f")] = round(data[t_key] * 1.8 + 32.0, 1)

        return {
            "device_id": "midnite",
            "device_name": "MidNite Solar Classic",
            "model": data.get("model_name", "Classic MPPT Charge Controller"),
            "online": True,
            "data": data,
            "registers": registers
        }

    def close(self):
        self.client.close()

