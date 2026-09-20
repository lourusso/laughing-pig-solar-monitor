import os
from pathlib import Path
from typing import Optional
import yaml
from pydantic import BaseModel, Field

class SystemConfig(BaseModel):
    name: str = "Laughing Pig Solar"
    poll_interval_seconds: int = 10
    log_level: str = "INFO"

class ClassicConfig(BaseModel):
    enabled: bool = True
    host: str = "192.168.42.129"
    port: int = 502
    unit_id: int = 1

class WebBoxUnits(BaseModel):
    webbox: int = 1
    sunny_island: int = 2
    sunny_boy: int = 4

class WebBoxDevices(BaseModel):
    sunny_island_key: str = "SI6048UM:1260044199"
    sunny_boy_key: str = "WR40U08E:2000702586"

class SunnyWebBoxConfig(BaseModel):
    enabled: bool = True
    host: str = "192.168.42.127"
    port: int = 502
    rpc_enabled: bool = True
    rpc_port: int = 80
    units: WebBoxUnits = Field(default_factory=WebBoxUnits)
    devices: WebBoxDevices = Field(default_factory=WebBoxDevices)

class ModbusConfig(BaseModel):
    timeout_seconds: float = 3.0
    classic: ClassicConfig = Field(default_factory=ClassicConfig)
    sunny_webbox: SunnyWebBoxConfig = Field(default_factory=SunnyWebBoxConfig)

class MQTTConfig(BaseModel):
    enabled: bool = True
    broker: str = "192.168.42.184"
    port: int = 1883
    username: str = ""
    password: str = ""
    topic_prefix: str = "laughing_pig_solar"
    homeassistant_discovery: bool = True

class StorageConfig(BaseModel):
    db_path: str = "data/solar.db"
    retention_days: int = 90

class WebConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8050

class AppConfig(BaseModel):
    system: SystemConfig = Field(default_factory=SystemConfig)
    modbus: ModbusConfig = Field(default_factory=ModbusConfig)
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
    if os.getenv("LPSM_WEBBOX_HOST"):
        config.modbus.sunny_webbox.host = os.getenv("LPSM_WEBBOX_HOST")
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
