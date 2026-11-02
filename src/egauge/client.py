import logging
import urllib.request
import xml.etree.ElementTree as ET
from typing import Dict, Any, List

logger = logging.getLogger("solar_monitor.egauge")

# ==============================================================================
# eGauge Energy Meter: The Farm's Electric Stethoscope!
# ==============================================================================
# What is an eGauge?
# Think of the eGauge like a super-smart electric stethoscope!
# Just like a doctor listens to your heartbeat through your chest without cutting
# you open, the eGauge uses little clip-on magnetic rings called "Current
# Transformers" (or CT clamps for short) that snap around electrical wires.
# It listens to the magnetic "buzz" of electricity flowing through the wire
# without ever touching bare copper or stopping the power!
#
# On our farm:
# - CT S1 listens to all the electricity flowing into the Main House.
# - CT S3 listens to the electricity flowing in the Shop (where the Sunny Boy
#   solar panels live).
#
# Both wires are 120-volt lines, so measuring one wire tells us exactly how much
# power our appliances and shop tools are drinking!
# ==============================================================================

class EGaugeClient:
    """
    Driver for eGauge EG3010 multi-channel energy meter.
    Queries the instantaneous XML endpoint (/cgi-bin/egauge?inst) over HTTP.
    
    CT S1: Main House Load (120V single conductor, Register did=0 'SI Load')
    CT S3: Shop Load (120V single conductor, Register did=16 'SB Power at Main House Load')
    """
    def __init__(
        self,
        host: str = "192.168.42.126",
        port: int = 80,
        timeout: float = 3.0,
        mac_address: str = "F8:2F:5B:01:33:F4"
    ):
        # The house number (IP address) where the eGauge lives on our private farm network
        self.host = host
        self.port = port
        self.timeout = timeout
        self.mac_address = mac_address
        self.base_url = f"http://{self.host}:{self.port}"
        self.serial: str = "0x1c7f464e"

    def poll(self) -> Dict[str, Any]:
        """
        Poll instantaneous telemetry from eGauge.
        
        We send a friendly note over the network to the eGauge:
        "Hello! Please tell us what the sensors are measuring right this second!"
        The eGauge replies in XML format (a digital recipe card).
        """
        url = f"{self.base_url}/cgi-bin/egauge?inst"
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "LaughingPigSolarMonitor/2.0"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                xml_data = resp.read()

            # Parse the XML "storybook" sent back by the eGauge
            tree = ET.fromstring(xml_data)
            self.serial = tree.attrib.get("serial", self.serial)

            s1_watts = 0.0
            s1_joules = 0.0
            s3_watts = 0.0
            s3_joules = 0.0
            frequency = 60.0

            raw_registers: List[Dict[str, Any]] = []

            # Inside the XML storybook, each sensor has its own chapter marked with an "<r>" tag
            for r in tree.findall("r"):
                name = r.attrib.get("n", "")
                did = r.attrib.get("did", "")
                rtype = r.attrib.get("t", "")
                val_el = r.find("v")    # <v> is cumulative energy in Joules
                inst_el = r.find("i")   # <i> is instantaneous power in Watts right now

                v_val = float(val_el.text) if val_el is not None and val_el.text else 0.0
                i_val = float(inst_el.text) if inst_el is not None and inst_el.text else 0.0

                unit = "W" if rtype == "P" else ("Hz" if rtype == "F" else ("V" if rtype == "V" else ("A" if rtype == "I" else "")))

                raw_registers.append({
                    "meta": f"did:{did}",
                    "name": name,
                    "type": rtype,
                    "value": f"{i_val:.2f}" if rtype in ("P", "F", "V", "I") else f"{i_val:.0f}",
                    "unit": unit,
                    "cumulative": f"{v_val:.0f}"
                })

                # Register 0: SI Load / Main House Load (CT S1)
                # This measures the electricity going to refrigerators, lights, and TVs in the house!
                if did == "0" or name.lower() == "si load" or name.lower() == "main house load":
                    s1_watts = i_val
                    s1_joules = v_val

                # Register 16: SB Power at Main House Load / Shop Load (CT S3)
                # This measures the electricity in the shop where tools and the Sunny Boy live!
                elif did == "16" or "sb power" in name.lower() or "shop load" in name.lower():
                    s3_watts = i_val
                    s3_joules = v_val

                # Register 17: Frequency
                # Electricity wiggles back and forth 60 times every second like a musical note (60 Hz)!
                elif did == "17" or rtype == "F" or "frequency" in name.lower():
                    frequency = i_val

            # Household electrical loads consume positive watts.
            # In eGauge settings, S1 formula is configured as -S1*L1, yielding positive draw.
            s1_watts = max(0.0, round(s1_watts, 1))
            s3_watts = max(0.0, round(s3_watts, 1))

            # Converting Joules to Kilowatt-Hours (kWh):
            # A Joule is 1 Watt of power for 1 second.
            # There are 3,600 seconds in an hour, and 1,000 Watts in a kiloWatt.
            # So 1 kiloWatt-Hour (kWh) = 1,000 Watts * 3,600 seconds = 3,600,000 Joules!
            # Dividing by 3,600,000 turns giant numbers of Joules into clean, familiar kWh!
            s1_kwh = round(s1_joules / 3600000.0, 2)
            s3_kwh = round(s3_joules / 3600000.0, 2)

            # Calculating Current (Amps):
            # Think of electricity like water in a pipe:
            # - Volts = Water pressure (here, 120 Volts)
            # - Amps = How much water flows through each second (Current)
            # - Watts = Total power (Watts = Volts * Amps)
            # To find Amps: Amps = Watts / 120 Volts!
            s1_amps = round(s1_watts / 120.0, 1) if s1_watts > 0 else 0.0
            s3_amps = round(s3_watts / 120.0, 1) if s3_watts > 0 else 0.0

            return {
                "online": True,
                "serial": self.serial,
                "mac": self.mac_address,
                "ip": self.host,
                "s1_house_load_watts": s1_watts,
                "s1_house_load_kwh": s1_kwh,
                "s1_house_load_amps": s1_amps,
                "s3_shop_load_watts": s3_watts,
                "s3_shop_load_kwh": s3_kwh,
                "s3_shop_load_amps": s3_amps,
                "frequency_hz": round(frequency, 2),
                "voltage_volts": 120.0,
                "raw_registers": raw_registers
            }

        except Exception as e:
            # If the eGauge is taking a nap or the network wire is unplugged:
            logger.debug(f"eGauge poll error from {self.host}: {e}")
            return {
                "online": False,
                "error": str(e),
                "serial": self.serial,
                "mac": self.mac_address,
                "ip": self.host,
                "s1_house_load_watts": 0.0,
                "s1_house_load_kwh": 0.0,
                "s1_house_load_amps": 0.0,
                "s3_shop_load_watts": 0.0,
                "s3_shop_load_kwh": 0.0,
                "s3_shop_load_amps": 0.0,
                "frequency_hz": 60.0,
                "voltage_volts": 120.0,
                "raw_registers": []
            }

    def poll_full(self) -> Dict[str, Any]:
        """
        Fetch full device telemetry payload for diagnostics view.
        This provides all the detailed raw register info for the Device Details popup.
        """
        data = self.poll()
        data["device_id"] = "egauge"
        data["device_name"] = "eGauge EG3010 Energy Meter"
        data["model"] = f"eGauge EG3010 Core (Static IP: {self.host})"
        data["mac_address"] = self.mac_address
        data["serial_number"] = self.serial
        data["channels"] = data.get("raw_registers", [])
        return data

    def close(self):
        """Cleanup connection if needed."""
        pass
