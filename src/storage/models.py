from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class TelemetrySnapshot(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # Solar PV Generation
    pv_dc_power_watts: float = 0.0     # MidNite Classic (Combined DC)
    pv_dc_volts: float = 0.0
    pv_dc_amps: float = 0.0
    pv_dc_daily_kwh: float = 0.0
    classic_bat_volts: float = 0.0     # MidNite Classic battery voltage
    charge_stage: str = "RESTING"

    # MidNite Classic #1 (192.168.42.129)
    classic1_power_watts: float = 0.0
    classic1_volts: float = 0.0
    classic1_amps: float = 0.0
    classic1_daily_kwh: float = 0.0
    classic1_bat_volts: float = 0.0
    classic1_stage: str = "RESTING"
    classic1_online: bool = False

    # MidNite Classic #2 (192.168.42.130)
    classic2_power_watts: float = 0.0
    classic2_volts: float = 0.0
    classic2_amps: float = 0.0
    classic2_daily_kwh: float = 0.0
    classic2_bat_volts: float = 0.0
    classic2_stage: str = "OFFLINE"
    classic2_online: bool = False

    pv_ac_power_watts: float = 0.0     # SMA Sunny Boy
    pv_ac_volts: float = 0.0
    pv_ac_total_kwh: float = 0.0

    total_pv_power_watts: float = 0.0  # DC + AC combined

    # Energy Storage (SMA Sunny Island & Discover Lithium)
    battery_soc: float = 0.0           # State of Charge %
    battery_soh: float = 100.0         # State of Health %
    battery_volts: float = 0.0
    battery_amps: float = 0.0          # Positive = charging, negative = discharging
    battery_power_watts: float = 0.0   # Positive = charging, negative = discharging
    battery_temp_c: float = 25.0

    # AC Distribution & Consumption
    load_power_watts: float = 0.0      # Household / farm electrical load
    grid_gen_power_watts: float = 0.0  # Generator or grid power input
    ac_frequency_hz: float = 60.0
    ac_voltage_volts: float = 120.0

    # System Health
    classic_online: bool = False
    webbox_online: bool = False
    warnings: Optional[str] = None

class DailySummary(BaseModel):
    date: str                          # YYYY-MM-DD
    pv_dc_kwh: float = 0.0
    pv_ac_kwh: float = 0.0
    total_pv_kwh: float = 0.0
    min_battery_soc: float = 0.0
    max_battery_soc: float = 0.0
    peak_pv_power_watts: float = 0.0
    peak_load_power_watts: float = 0.0
