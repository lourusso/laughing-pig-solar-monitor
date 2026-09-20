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

    def close(self):
        self.client.close()
