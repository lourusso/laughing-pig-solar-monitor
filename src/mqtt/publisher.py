import json
import logging
from typing import Dict, Any, Optional
import paho.mqtt.client as mqtt
from ..storage.models import TelemetrySnapshot

logger = logging.getLogger(__name__)

class MQTTPublisher:
    def __init__(
        self,
        broker: str = "192.168.42.184",
        port: int = 1883,
        username: str = "",
        password: str = "",
        topic_prefix: str = "laughing_pig_solar",
        ha_discovery: bool = True
    ):
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.topic_prefix = topic_prefix.rstrip("/")
        self.ha_discovery = ha_discovery
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="laughing_pig_monitor")
        self._connected = False
        self._discovery_sent = False

        if username:
            self.client.username_pw_set(username, password)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    def start(self):
        try:
            self.client.connect_async(self.broker, self.port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            logger.warning(f"Could not initiate MQTT connection to {self.broker}:{self.port}: {e}")

    def stop(self):
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info(f"Connected to MQTT broker at {self.broker}:{self.port}")
            self._connected = True
            if self.ha_discovery and not self._discovery_sent:
                self.publish_ha_discovery()
                self._discovery_sent = True
        else:
            logger.warning(f"MQTT connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, flags, rc, properties=None):
        logger.info(f"Disconnected from MQTT broker (rc={rc})")
        self._connected = False

    def publish_snapshot(self, snapshot: TelemetrySnapshot):
        if not self._connected:
            return

        payload = snapshot.model_dump()
        state_topic = f"{self.topic_prefix}/state"
        
        try:
            self.client.publish(state_topic, json.dumps(payload), qos=0, retain=True)

            # Also publish individual key topics
            sub_topics = {
                "solar/total_power": snapshot.total_pv_power_watts,
                "solar/dc_power": snapshot.pv_dc_power_watts,
                "solar/classic_bat_volts": snapshot.classic_bat_volts,
                "solar/ac_power": snapshot.pv_ac_power_watts,
                "battery/soc": snapshot.battery_soc,
                "battery/volts": snapshot.battery_volts,
                "battery/amps": snapshot.battery_amps,
                "battery/power": snapshot.battery_power_watts,
                "load/power": snapshot.load_power_watts,
                "grid_gen/power": snapshot.grid_gen_power_watts,
            }
            for sub, val in sub_topics.items():
                self.client.publish(f"{self.topic_prefix}/{sub}", str(val), qos=0, retain=True)

        except Exception as e:
            logger.warning(f"Failed to publish MQTT snapshot: {e}")

    def publish_ha_discovery(self):
        """Publish Home Assistant MQTT Auto-Discovery sensor configurations."""
        dev_info = {
            "identifiers": ["laughing_pig_solar_monitor"],
            "name": "Laughing Pig Solar System",
            "model": "Hybrid Solar & Battery Hub",
            "manufacturer": "MidNite / SMA / Discover"
        }
        state_topic = f"{self.topic_prefix}/state"

        sensors = [
            {
                "id": "battery_soc",
                "name": "Battery State of Charge",
                "unit": "%",
                "dev_cla": "battery",
                "stat_cla": "measurement",
                "val_tpl": "{{ value_json.battery_soc }}"
            },
            {
                "id": "battery_power",
                "name": "Battery Power",
                "unit": "W",
                "dev_cla": "power",
                "stat_cla": "measurement",
                "val_tpl": "{{ value_json.battery_power_watts }}"
            },
            {
                "id": "battery_voltage",
                "name": "Battery Voltage",
                "unit": "V",
                "dev_cla": "voltage",
                "stat_cla": "measurement",
                "val_tpl": "{{ value_json.battery_volts }}"
            },
            {
                "id": "total_solar_power",
                "name": "Total Solar Power",
                "unit": "W",
                "dev_cla": "power",
                "stat_cla": "measurement",
                "val_tpl": "{{ value_json.total_pv_power_watts }}"
            },
            {
                "id": "dc_solar_power",
                "name": "MidNite DC Solar Power",
                "unit": "W",
                "dev_cla": "power",
                "stat_cla": "measurement",
                "val_tpl": "{{ value_json.pv_dc_power_watts }}"
            },
            {
                "id": "ac_solar_power",
                "name": "Sunny Boy AC Solar Power",
                "unit": "W",
                "dev_cla": "power",
                "stat_cla": "measurement",
                "val_tpl": "{{ value_json.pv_ac_power_watts }}"
            },
            {
                "id": "load_power",
                "name": "Household Load Power",
                "unit": "W",
                "dev_cla": "power",
                "stat_cla": "measurement",
                "val_tpl": "{{ value_json.load_power_watts }}"
            },
            {
                "id": "grid_gen_power",
                "name": "Generator / Grid Power",
                "unit": "W",
                "dev_cla": "power",
                "stat_cla": "measurement",
                "val_tpl": "{{ value_json.grid_gen_power_watts }}"
            },
            {
                "id": "dc_solar_daily_yield",
                "name": "MidNite Daily Solar Yield",
                "unit": "kWh",
                "dev_cla": "energy",
                "stat_cla": "total_increasing",
                "val_tpl": "{{ value_json.pv_dc_daily_kwh }}"
            },
            {
                "id": "charge_stage",
                "name": "MidNite Charge Stage",
                "val_tpl": "{{ value_json.charge_stage }}"
            }
        ]

        for s in sensors:
            discovery_topic = f"homeassistant/sensor/laughing_pig_{s['id']}/config"
            payload = {
                "name": s["name"],
                "unique_id": f"lpsm_{s['id']}",
                "state_topic": state_topic,
                "value_template": s["val_tpl"],
                "device": dev_info
            }
            if "unit" in s:
                payload["unit_of_measurement"] = s["unit"]
            if "dev_cla" in s:
                payload["device_class"] = s["dev_cla"]
            if "stat_cla" in s:
                payload["state_class"] = s["stat_cla"]

            try:
                self.client.publish(discovery_topic, json.dumps(payload), qos=1, retain=True)
            except Exception as e:
                logger.warning(f"Failed to publish HA discovery for {s['id']}: {e}")

        logger.info("Published Home Assistant MQTT Auto-Discovery topics.")
