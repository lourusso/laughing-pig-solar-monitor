from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

# ==============================================================================
# Telemetry Snapshot: A High-Speed Camera Photo of Farm Energy!
# ==============================================================================
# Think of a TelemetrySnapshot like taking a fast camera photo of our whole solar
# power system every few seconds!
#
# In that one single photo, we freeze time and capture:
# 1. Solar Panels: How much sunshine is turning into electric power (Watts)
# 2. Batteries: How full our lithium battery fuel tank is (State of Charge %)
# 3. Farm Loads: How much electricity the house and shop are drinking right now
# 4. Gadget Health: Whether our computers and inverters are awake and smiling!
#
# Every snapshot gets stamped with the exact date and time (UTC) so we can look
# back in our digital photo album anytime!
# ==============================================================================

class TelemetrySnapshot(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # --------------------------------------------------------------------------
    # Solar PV Generation (Harvesting Sunshine!)
    # --------------------------------------------------------------------------
    # DC Solar: Power from MidNite Classic controllers.
    # Think of this like drinking sunshine straight into the battery tank!
    pv_dc_power_watts: float = 0.0     # MidNite Classic (Combined DC)
    pv_dc_volts: float = 0.0           # Electrical pressure coming down from the roof
    pv_dc_amps: float = 0.0            # Flow speed of solar electricity
    pv_dc_daily_kwh: float = 0.0       # Total energy collected today in kilowatt-hours
    classic_bat_volts: float = 0.0     # Battery voltage measured at the charge controller
    charge_stage: str = "RESTING"      # What the solar charger is doing (BULK, ABSORB, FLOAT, or RESTING at night)

    # MidNite Classic #1 (Living at 192.168.42.129)
    classic1_power_watts: float = 0.0
    classic1_volts: float = 0.0
    classic1_amps: float = 0.0
    classic1_daily_kwh: float = 0.0
    classic1_bat_volts: float = 0.0
    classic1_stage: str = "RESTING"
    classic1_online: bool = False

    # MidNite Classic #2 (Living at 192.168.42.130)
    classic2_power_watts: float = 0.0
    classic2_volts: float = 0.0
    classic2_amps: float = 0.0
    classic2_daily_kwh: float = 0.0
    classic2_bat_volts: float = 0.0
    classic2_stage: str = "OFFLINE"
    classic2_online: bool = False

    # AC Solar: Power from the SMA Sunny Boy inverter out in the shop.
    # It converts high-voltage solar panels directly into household wall-outlet AC power!
    pv_ac_power_watts: float = 0.0     # SMA Sunny Boy current generation
    pv_ac_volts: float = 0.0           # AC grid voltage
    pv_ac_total_kwh: float = 0.0       # All-time solar energy made since installation

    # Total Sunshine: DC solar plus AC solar added together!
    total_pv_power_watts: float = 0.0  # DC + AC combined

    # --------------------------------------------------------------------------
    # Energy Storage (Our Giant Discover Lithium Battery Bank!)
    # --------------------------------------------------------------------------
    battery_soc: float = 0.0           # State of Charge % (like the battery fuel gauge on a tablet!)
    battery_soh: float = 100.0         # State of Health % (100% means brand new and healthy!)
    battery_volts: float = 0.0         # Battery electrical voltage (~52V is standard for 48V banks)
    battery_amps: float = 0.0          # Positive (+) = charging up; Negative (-) = powering appliances
    battery_power_watts: float = 0.0   # Power flowing in (+) or out (-) of the battery
    battery_temp_c: float = 25.0       # Battery temperature in Celsius
    battery_temp_f: float = 77.0       # Battery temperature in Fahrenheit (comfortable room temp!)

    # --------------------------------------------------------------------------
    # AC Distribution & Farm Loads (The Appliances Drinking Power!)
    # --------------------------------------------------------------------------
    load_power_watts: float = 0.0      # Total Farm electrical load (Main House + Shop)
    grid_gen_power_watts: float = 0.0  # Generator backup power input if the backup engine runs
    generator_volts: float = 0.0       # Generator voltage
    generator_amps: float = 0.0        # Generator current
    generator_frequency: float = 0.0   # Generator AC speed
    ac_frequency_hz: float = 60.0      # Grid frequency: 60 wiggles per second (60 Hz)
    ac_voltage_volts: float = 120.0    # Standard household wall socket voltage (120V)

    # --------------------------------------------------------------------------
    # eGauge EG3010 Energy Meter (Our Electric Stethoscope!)
    # --------------------------------------------------------------------------
    egauge_online: bool = False
    house_load_watts: float = 0.0      # Main House 120V Load (measured by CT clamp S1)
    shop_load_watts: float = 0.0       # Shop 120V Load (measured by CT clamp S3 & Sunny Boy math)
    load_source: str = "eGauge S1"

    # --------------------------------------------------------------------------
    # System Health (Checking if our gadgets are awake and happy)
    # --------------------------------------------------------------------------
    classic_online: bool = False
    webbox_online: bool = False
    sunnyboy_online: bool = False
    warnings: Optional[str] = None


# ==============================================================================
# Daily Summary: The Farm's Daily Solar Report Card!
# ==============================================================================
# At the end of each day when the sun sets, this report card remembers:
# - How many kilowatt-hours of solar energy we harvested
# - The highest solar power spike (Peak Watts)
# - The lowest and highest battery levels
# ==============================================================================

class DailySummary(BaseModel):
    date: str                          # YYYY-MM-DD
    pv_dc_kwh: float = 0.0
    pv_ac_kwh: float = 0.0
    total_pv_kwh: float = 0.0
    min_battery_soc: float = 0.0
    max_battery_soc: float = 0.0
    peak_pv_power_watts: float = 0.0
    peak_load_power_watts: float = 0.0
