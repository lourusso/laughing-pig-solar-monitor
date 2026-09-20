import socket
import struct
import threading
import time
from typing import List, Optional, Union

class ModbusError(Exception):
    pass

class ModbusTCPClient:
    """
    Robust socket-based Modbus TCP client.
    Thread-safe, handles automatic reconnection, timeouts, and multi-word decoding.
    """
    def __init__(self, host: str, port: int = 502, timeout: float = 3.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._tx_id = 1

    def _get_tx_id(self) -> int:
        self._tx_id = (self._tx_id + 1) & 0xFFFF
        if self._tx_id == 0:
            self._tx_id = 1
        return self._tx_id

    def connect(self) -> bool:
        with self._lock:
            return self._connect_locked()

    def _connect_locked(self) -> bool:
        if self._sock is not None:
            return True
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            s.connect((self.host, self.port))
            self._sock = s
            return True
        except Exception as e:
            self._sock = None
            raise ModbusError(f"Connection failed to {self.host}:{self.port}: {e}")

    def close(self):
        with self._lock:
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None

    def read_holding_registers(self, unit_id: int, address: int, count: int) -> List[int]:
        """Read holding registers (Function Code 0x03)"""
        return self._send_read_request(function_code=3, unit_id=unit_id, address=address, count=count)

    def read_input_registers(self, unit_id: int, address: int, count: int) -> List[int]:
        """Read input registers (Function Code 0x04)"""
        return self._send_read_request(function_code=4, unit_id=unit_id, address=address, count=count)

    def _send_read_request(self, function_code: int, unit_id: int, address: int, count: int) -> List[int]:
        with self._lock:
            # Ensure connected
            if self._sock is None:
                self._connect_locked()

            tx_id = self._get_tx_id()
            proto_id = 0
            pdu = struct.pack('>BHH', function_code, address, count)
            length = len(pdu) + 1  # includes unit_id
            header = struct.pack('>HHHB', tx_id, proto_id, length, unit_id)
            packet = header + pdu

            try:
                assert self._sock is not None
                self._sock.sendall(packet)

                # Read Modbus MBAP Header (7 bytes)
                resp_header = self._recv_exact(7)
                resp_tx_id, resp_proto, resp_len, resp_uid = struct.unpack('>HHHB', resp_header)

                if resp_proto != 0:
                    raise ModbusError(f"Invalid Modbus protocol ID: {resp_proto}")

                # Read remaining PDU bytes
                remaining_len = resp_len - 1
                resp_pdu = self._recv_exact(remaining_len)

                resp_fc = resp_pdu[0]
                if resp_fc & 0x80:
                    exception_code = resp_pdu[1] if len(resp_pdu) > 1 else -1
                    raise ModbusError(f"Modbus Exception 0x{exception_code:02X} from {self.host} (Unit {unit_id}, Reg {address})")

                if resp_fc != function_code:
                    raise ModbusError(f"Unexpected Function Code: expected {function_code}, got {resp_fc}")

                byte_count = resp_pdu[1]
                data = resp_pdu[2:2 + byte_count]

                registers = [struct.unpack('>H', data[i:i + 2])[0] for i in range(0, len(data), 2)]
                return registers

            except (socket.timeout, socket.error, ModbusError) as e:
                # Force reset socket on network error
                if self._sock:
                    try:
                        self._sock.close()
                    except Exception:
                        pass
                    self._sock = None
                raise ModbusError(f"Modbus transaction failed ({self.host}:{self.port}, unit {unit_id}, addr {address}): {e}")

    def _recv_exact(self, num_bytes: int) -> bytes:
        buf = bytearray()
        assert self._sock is not None
        while len(buf) < num_bytes:
            chunk = self._sock.recv(num_bytes - len(buf))
            if not chunk:
                raise ModbusError("Socket closed prematurely by peer")
            buf.extend(chunk)
        return bytes(buf)

# Utility decoder functions
def to_signed_16(val: int) -> int:
    return struct.unpack('>h', struct.pack('>H', val))[0]

def to_uint_32(high: int, low: int) -> int:
    return (high << 16) | low

def to_int_32(high: int, low: int) -> int:
    raw = (high << 16) | low
    return struct.unpack('>i', struct.pack('>I', raw))[0]
