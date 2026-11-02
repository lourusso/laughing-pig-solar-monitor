# ==============================================================================
# The Configuration Recipe Book for the Laughing Pig Solar Monitor!
# ==============================================================================
# Think of this file like a master recipe card for our solar monitor program.
# It tells our computer where every gadget lives on the farm's network (their IP
# address, like their house number), what language to speak with them, and how
# often to go check on them!
# ==============================================================================

import os
from pathlib import Path
from typing import Optional
import yaml
from pydantic import BaseModel, Field

# Overall rules for the whole solar monitor system
class SystemConfig(BaseModel):
    name: str = "Laughing Pig Solar"
    # How many seconds to wait before checking the solar panels again!
    # Every 3 seconds matches the web browser refresh rate so the numbers on screen
    # are always brand-new and lightning fast!
    poll_interval_seconds: int = 3
    # How chatty the monitor should be in its logbook ("INFO" means write down the important milestones)
    log_level: str = "INFO"

# Settings for MidNite Classic #1 - our first solar charge controller that drinks sunlight and charges batteries
class ClassicConfig(BaseModel):
    enabled: bool = True
    # The house number (IP address) of Classic #1 on the local farm Wi-Fi/Ethernet network
    host: str = "192.168.42.129"
    # Port 502 is the special door number used for Modbus industrial conversations
    port: int = 502
    unit_id: int = 1

# Special ID badges for devices connected to the SMA WebBox translator
class WebBoxUnits(BaseModel):
    webbox: int = 1
    sunny_island: int = 2
    sunny_boy: int = 4

# Unique factory serial names so the WebBox knows which gadget is which
class WebBoxDevices(BaseModel):
    sunny_island_key: str = "SI6048UM:1260044199"
    sunny_boy_key: str = "WR40U08E:2000702586"

# Settings for the SMA Sunny WebBox - the smart translator that talks to both the Sunny Island inverter and Sunny Boy
class SunnyWebBoxConfig(BaseModel):
    enabled: bool = True
    # Network IP address of the WebBox
    host: str = "192.168.42.127"
    port: int = 502
    # RPC is a friendly web format (JSON) that lets the WebBox send us rich data packets
    rpc_enabled: bool = True
    rpc_port: int = 80
    units: WebBoxUnits = Field(default_factory=WebBoxUnits)
    devices: WebBoxDevices = Field(default_factory=WebBoxDevices)

# Settings for MidNite Classic #2 - our second solar charge controller
class Classic2Config(BaseModel):
    enabled: bool = True
    # Network IP address of Classic #2
    host: str = "192.168.42.130"
    port: int = 502
    unit_id: int = 1

# Modbus conversation rules (how long to wait if a device doesn't pick up the phone)
class ModbusConfig(BaseModel):
    # If a controller doesn't answer in 3 seconds, don't wait forever—move on!
    timeout_seconds: float = 3.0
    classic: ClassicConfig = Field(default_factory=ClassicConfig)
    classic2: Classic2Config = Field(default_factory=Classic2Config)
    sunny_webbox: SunnyWebBoxConfig = Field(default_factory=SunnyWebBoxConfig)

# Settings for the eGauge EG3010 - the electrical stethoscope with clamp sensors
class EGaugeConfig(BaseModel):
    enabled: bool = True
    # Network IP address of the eGauge meter
    host: str = "192.168.42.126"
    port: int = 80
    timeout_seconds: float = 3.0
    mac_address: str = "F8:2F:5B:01:33:F4"
    # When True, calculates Total Farm Load = ((SB4000 Solar - S3 Shop) + S1 House)
    use_for_farm_loads: bool = True
    use_s1_for_house_loads: bool = True

# MQTT lets our monitor send real-time radio broadcasts to smart home dashboards like Home Assistant
class MQTTConfig(BaseModel):
    enabled: bool = True
    broker: str = "192.168.42.184"
    port: int = 1883
    username: str = ""
    password: str = ""
    topic_prefix: str = "laughing_pig_solar"
    homeassistant_discovery: bool = True

# Where the monitor saves its diary of snapshots so we can look back at history
class StorageConfig(BaseModel):
    db_path: str = "data/solar.db"
    # Keep full high-speed 15-second snapshots for a whole year (365 days)!
    retention_days: int = 365
    # After 365 days, instead of throwing old history in the trash, we neatly
    # average every 10 minutes of readings into a single summary row forever!
    rollup_interval_minutes: int = 10
    # Even though we check the solar panels every 3 seconds for the live screen,
    # we only write in the disk notebook every 15 seconds so the hard drive stays cool and relaxed!
    db_save_interval_seconds: int = 15

# The web dashboard server settings (what port to visit in your web browser!)
class WebConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8050

# The master container holding all the settings together
class AppConfig(BaseModel):
    system: SystemConfig = Field(default_factory=SystemConfig)
    modbus: ModbusConfig = Field(default_factory=ModbusConfig)
    egauge: EGaugeConfig = Field(default_factory=EGaugeConfig)
    mqtt: MQTTConfig = Field(default_factory=MQTTConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    web: WebConfig = Field(default_factory=WebConfig)

def load_config(config_path: Optional[str] = None) -> AppConfig:
    # Resolve config path
    if not config_path:
        default_paths = [
            Path("config/config.yaml"),
            Path("/app/config/config.yaml"),
            Path(__file__).parent.parent / "config" / "config.yaml",
        ]
        for p in default_paths:
            if p.exists():
                config_path = str(p)
                break

    data = {}
    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    config = AppConfig(**data)

    # Check environment variable overrides
    if os.getenv("LPSM_CLASSIC_HOST"):
        config.modbus.classic.host = os.getenv("LPSM_CLASSIC_HOST")
    if os.getenv("LPSM_CLASSIC2_HOST"):
        config.modbus.classic2.host = os.getenv("LPSM_CLASSIC2_HOST")
    if os.getenv("LPSM_WEBBOX_HOST"):
        config.modbus.sunny_webbox.host = os.getenv("LPSM_WEBBOX_HOST")
    if os.getenv("LPSM_EGAUGE_HOST"):
        config.egauge.host = os.getenv("LPSM_EGAUGE_HOST")
    if os.getenv("LPSM_MQTT_BROKER"):
        config.mqtt.broker = os.getenv("LPSM_MQTT_BROKER")
    if os.getenv("LPSM_MQTT_PORT"):
        config.mqtt.port = int(os.getenv("LPSM_MQTT_PORT"))
    if os.getenv("LPSM_MQTT_USER"):
        config.mqtt.username = os.getenv("LPSM_MQTT_USER")
    if os.getenv("LPSM_MQTT_PASSWORD"):
        config.mqtt.password = os.getenv("LPSM_MQTT_PASSWORD")
    if os.getenv("LPSM_WEB_PORT"):
        config.web.port = int(os.getenv("LPSM_WEB_PORT"))
    if os.getenv("LPSM_POLL_INTERVAL"):
        config.system.poll_interval_seconds = int(os.getenv("LPSM_POLL_INTERVAL"))
    if os.getenv("LPSM_DB_PATH"):
        config.storage.db_path = os.getenv("LPSM_DB_PATH")

    return config
