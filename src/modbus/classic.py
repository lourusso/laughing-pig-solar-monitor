import logging
from typing import Dict, Any, Optional
from .client import ModbusTCPClient, ModbusError, to_signed_16, to_uint_32

logger = logging.getLogger(__name__)

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

class MidNiteClassic:
    """
    Driver for MidNite Solar Classic MPPT Charge Controller via Modbus TCP.
    Reads real-time PV generation, battery charging stage, and temperatures.
    """
    def __init__(self, host: str = "192.168.42.129", port: int = 502, unit_id: int = 1, timeout: float = 3.0):
        self.client = ModbusTCPClient(host=host, port=port, timeout=timeout)
        self.unit_id = unit_id
        self.host = host

    def poll(self) -> Dict[str, Any]:
        """Poll the Classic and return parsed telemetry."""
        try:
            # Read block from register 4115 to 4140 (26 registers)
            # Modbus 0-based address for register 4115 is 4114
            regs = self.client.read_holding_registers(unit_id=self.unit_id, address=4114, count=26)

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
            
            # 4126 & 4127: Lifetime Energy Total (kWh)
            # Reg 4126 is low word, 4127 is high word
            lifetime_low = regs[11]
            lifetime_high = regs[12]
            total_kwh = ((lifetime_high << 16) + lifetime_low) / 10.0

            # 4132: Battery temperature, 4133: FET temp, 4134: PCB temp
            bat_temp = to_signed_16(regs[17]) / 10.0 if len(regs) > 17 else 25.0
            fet_temp = to_signed_16(regs[18]) / 10.0 if len(regs) > 18 else 25.0
            pcb_temp = to_signed_16(regs[19]) / 10.0 if len(regs) > 19 else 25.0

            return {
                "online": True,
                "pv_power_watts": power_watts,
                "pv_voltage": pv_voltage,
                "pv_current": pv_current,
                "pv_voc": voc_volts,
                "battery_voltage": bat_voltage,
                "battery_current": bat_current,
                "energy_today_kwh": energy_today,
                "energy_total_kwh": total_kwh,
                "charge_stage": stage_str,
                "pcb_temp_c": pcb_temp,
                "fet_temp_c": fet_temp,
                "battery_temp_c": bat_temp,
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

        # Helper to format seconds
        def fmt_time(sec: int) -> str:
            h = sec // 3600
            m = (sec % 3600) // 60
            s = sec % 60
            if h > 0:
                return f"{h}h {m}m {s}s"
            if m > 0:
                return f"{m}m {s}s"
            return f"{s}s"

        # 1. Read Block 4115 - 4144 (30 registers from 4114)
        try:
            regs_main = self.client.read_holding_registers(unit_id=self.unit_id, address=4114, count=30)
            
            data["pv_highest_v"] = regs_main[8] / 10.0 if len(regs_main) > 8 else 0.0
            data["amphours_today"] = regs_main[10] if len(regs_main) > 10 else 0
            
            if len(regs_main) > 14:
                data["lifetime_amphours"] = (regs_main[14] << 16) + regs_main[13]
            else:
                data["lifetime_amphours"] = 0

            data["night_minutes"] = regs_main[20] if len(regs_main) > 20 else 0
            data["float_time_today_sec"] = regs_main[23] if len(regs_main) > 23 else 0
            data["float_time_today_str"] = fmt_time(data["float_time_today_sec"])
            
            data["absorb_time_sec"] = regs_main[24] if len(regs_main) > 24 else 0
            data["absorb_time_str"] = fmt_time(data["absorb_time_sec"])
            
            data["pwm_duty"] = regs_main[26] if len(regs_main) > 26 else 0
            data["reset_reason"] = regs_main[27] if len(regs_main) > 27 else 0
            
            data["equalize_time_sec"] = regs_main[28] if len(regs_main) > 28 else 0
            data["equalize_time_str"] = fmt_time(data["equalize_time_sec"])

            # Register entries for table
            reg_defs_main = [
                (4115, "dispavgVbatt", "Average Battery Voltage", f"{data['battery_voltage']} V"),
                (4116, "dispavgVpv", "Average PV Input Voltage", f"{data['pv_voltage']} V"),
                (4117, "IbattDisplayS", "Average Battery Current", f"{data['battery_current']} A"),
                (4118, "kW-Hours", "Daily Solar Energy Yield", f"{data['energy_today_kwh']} kWh"),
                (4119, "Watts", "Instantaneous Power", f"{data['pv_power_watts']} W"),
                (4120, "ComboChargeStage", "Active Charge Stage", data['charge_stage']),
                (4121, "PvInputCurrent", "Average PV Input Current", f"{data['pv_current']} A"),
                (4122, "VocLastMeasured", "Last Measured Voc", f"{data['pv_voc']} V"),
                (4123, "HighestVinputLog", "Highest PV Input Voltage", f"{data['pv_highest_v']} V"),
                (4125, "AmpHours", "Daily Amp-Hours", f"{data['amphours_today']} Ah"),
                (4126, "Lifetime kW-Hours", "Lifetime Energy Generation", f"{data['energy_total_kwh']} kWh"),
                (4128, "LifetimeAmpHours", "Lifetime Amp-Hours", f"{data['lifetime_amphours']} Ah"),
                (4132, "BATTtemperature", "Battery Temp Sensor", f"{data['battery_temp_c']} °C ({data['battery_temp_c']*1.8+32:.1f} °F)"),
                (4133, "FETtemperature", "Power FET Temperature", f"{data['fet_temp_c']} °C ({data['fet_temp_c']*1.8+32:.1f} °F)"),
                (4134, "PCBTemperature", "PCB Control Board Temp", f"{data['pcb_temp_c']} °C ({data['pcb_temp_c']*1.8+32:.1f} °F)"),
                (4135, "NiteMinutesNoPwr", "Night Minutes (No Solar)", f"{data['night_minutes']} min"),
                (4138, "FloatTimeToday", "Time in Float Stage Today", data['float_time_today_str']),
                (4139, "AbsorbTime", "Absorb Time Counter", data['absorb_time_str']),
                (4141, "PWM_ReadOnly", "PWM Duty Cycle Command", f"{data['pwm_duty']}"),
                (4142, "Reason_For_Reset", "Reset Reason Code", f"{data['reset_reason']}"),
                (4143, "Equalize Time", "Equalize Time Remaining", data['equalize_time_str'])
            ]
            for r_num, r_name, r_desc, r_val in reg_defs_main:
                registers.append({"register": r_num, "name": r_name, "description": r_desc, "value": r_val})

        except Exception as e:
            logger.debug(f"Could not read extended registers 4115-4144: {e}")

        # 2. Read Block 4101 - 4114 (14 registers from 4100): Unit info & build date
        try:
            regs_info = self.client.read_holding_registers(unit_id=self.unit_id, address=4100, count=14)
            if len(regs_info) >= 8:
                pcb_rev = (regs_info[0] >> 8) & 0xFF
                unit_code = regs_info[0] & 0xFF
                model_map = {150: "Classic 150", 200: "Classic 200", 250: "Classic 250", 251: "Classic 250-KS"}
                model_str = model_map.get(unit_code, f"Classic {unit_code}")
                data["model_name"] = model_str
                data["pcb_rev"] = pcb_rev
                
                yr = regs_info[1]
                mo = (regs_info[2] >> 8) & 0xFF
                dy = regs_info[2] & 0xFF
                data["sw_date"] = f"{yr:04d}-{mo:02d}-{dy:02d}"
                
                mac_bytes = [
                    (regs_info[7] >> 8) & 0xFF, regs_info[7] & 0xFF,
                    (regs_info[6] >> 8) & 0xFF, regs_info[6] & 0xFF,
                    (regs_info[5] >> 8) & 0xFF, regs_info[5] & 0xFF
                ]
                data["mac_address"] = ":".join(f"{b:02X}" for b in mac_bytes)
                if len(regs_info) >= 12:
                    data["device_id"] = (regs_info[11] << 16) + regs_info[10]
                
                registers.extend([
                    {"register": 4101, "name": "UNIT_ID", "description": "Model & PCB Revision", "value": f"{model_str} (PCB Rev {pcb_rev})"},
                    {"register": 4102, "name": "UNIT_SW_DATE", "description": "Firmware Build Date", "value": data.get("sw_date", "--")},
                    {"register": 4106, "name": "UNIT_MAC_Address", "description": "Ethernet MAC Address", "value": data.get("mac_address", "--")},
                    {"register": 4111, "name": "UNIT_Device_ID", "description": "Factory Unit Device ID", "value": str(data.get("device_id", "--"))}
                ])
        except Exception as e:
            logger.debug(f"Could not read unit info registers: {e}")

        # 3. Read Block 4153 - 4165 (13 registers from 4152): Setpoints & Configuration
        try:
            regs_cfg = self.client.read_holding_registers(unit_id=self.unit_id, address=4152, count=13)
            if len(regs_cfg) >= 12:
                data["absorb_setpoint_sec"] = regs_cfg[1]
                data["absorb_setpoint_str"] = fmt_time(regs_cfg[1])
                data["max_temp_comp_v"] = regs_cfg[2] / 10.0
                data["min_temp_comp_v"] = regs_cfg[3] / 10.0
                data["temp_comp_mv_c_cell"] = -(regs_cfg[4] / 10.0)
                data["equalize_setpoint_sec"] = regs_cfg[9]
                data["equalize_setpoint_str"] = fmt_time(regs_cfg[9])
                data["equalize_interval_days"] = regs_cfg[10]
                
                mppt_mode_code = regs_cfg[11]
                mppt_modes = {0: "Solar", 1: "PV U-Set", 2: "Wind Track", 3: "Dynamic", 4: "U-Set 2"}
                data["mppt_mode"] = mppt_modes.get(mppt_mode_code, f"Mode {mppt_mode_code}")

                registers.extend([
                    {"register": 4154, "name": "Absorb Time Setpoint", "description": "Absorb Duration Setting", "value": data["absorb_setpoint_str"]},
                    {"register": 4155, "name": "Max Temp Comp Volts", "description": "Maximum Temp-Comp Voltage", "value": f"{data['max_temp_comp_v']} V"},
                    {"register": 4156, "name": "Min Temp Comp Volts", "description": "Minimum Temp-Comp Voltage", "value": f"{data['min_temp_comp_v']} V"},
                    {"register": 4157, "name": "Temp Comp Slope", "description": "Battery Temp Compensation", "value": f"{data['temp_comp_mv_c_cell']} mV/°C/cell"},
                    {"register": 4162, "name": "Equalize Time Setpoint", "description": "Equalize Duration Setting", "value": data["equalize_setpoint_str"]},
                    {"register": 4163, "name": "Equalize Interval", "description": "Auto-Equalize Interval", "value": f"{data['equalize_interval_days']} Days"},
                    {"register": 4164, "name": "MPPT Mode", "description": "Tracking Algorithm Mode", "value": data["mppt_mode"]}
                ])
        except Exception as e:
            logger.debug(f"Could not read setpoint registers 4153-4165: {e}")

        # 4. Read Block 4244 - 4250 (7 registers from 4243): Regulation & nominal battery voltage
        try:
            regs_reg = self.client.read_holding_registers(unit_id=self.unit_id, address=4243, count=7)
            if len(regs_reg) >= 6:
                data["temp_comp_target_v"] = regs_reg[0] / 10.0
                data["nominal_bat_v"] = regs_reg[1]
                data["ending_amps"] = regs_reg[2] / 10.0
                data["rebulk_v"] = regs_reg[5] / 10.0

                registers.extend([
                    {"register": 4244, "name": "VbattRegSetPTmpComp", "description": "Temp-Compensated Regulation Target", "value": f"{data['temp_comp_target_v']} V"},
                    {"register": 4245, "name": "VbattNominal", "description": "Nominal Battery Bank Voltage", "value": f"{data['nominal_bat_v']} V"},
                    {"register": 4246, "name": "EndingAmps", "description": "Absorb Ending Current", "value": f"{data['ending_amps']} A"},
                    {"register": 4249, "name": "RebulkVolts", "description": "Rebulk Trigger Voltage", "value": f"{data['rebulk_v']} V"}
                ])
        except Exception as e:
            logger.debug(f"Could not read regulation registers 4244-4250: {e}")

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

