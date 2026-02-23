"""
Modbus TCP client for Heidelberg Amperfied Wallbox.

Author: XtremerNL
Version: 0.9.20
"""

import socket
import struct
import random
import time
import Domoticz

# Modbus protocol constants
MODBUS_READ_INPUT_REGISTERS = 0x04
MODBUS_READ_HOLDING_REGISTERS = 0x03
MODBUS_WRITE_HOLDING_REGISTER = 0x06
MODBUS_EXCEPTION_MASK = 0x80

# Wallbox charging states and descriptions
CHARGING_STATE_TEXT = {
    2: "Geen auto aangesloten, Wallbox geblokkeerd.",
    3: "Geen auto aangesloten, Wallbox vrijgegeven.",
    4: "Aangesloten zonder laadverzoek, Wallbox geblokkeerd.",
    5: "Aangesloten zonder laadverzoek, Wallbox vrijgegeven.",
    6: "Wacht op laden, Wallbox geblokkeerd.",
    7: "Auto laden.",
    8: "Laadvermogen terugregelen.",
    9: "Fout. (9)",
    10: "Wallbox vergrendeld of niet klaar.",
    11: "Fout. (11)"
}


class HeidelbergWallbox:
    """
    Snelle, persistente Modbus TCP client met minimale logging.
    """

    def __init__(self, ip: str, port: int, unit_id: int, timeout: float = 0.5, debug=False):
        self.ip = ip
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self.debug = debug

        self._sock = None
        self._last_used = 0.0
        self._idle_timeout = 30.0

    def dbg(self, msg):
        if self.debug:
            Domoticz.Log("[WB DEBUG] " + str(msg))

    # ---------------------------------------------------------
    # SOCKET MANAGEMENT
    # ---------------------------------------------------------

    def _ensure_socket(self):
        now = time.time()

        if self._sock is not None and (now - self._last_used) > self._idle_timeout:
            self._close_socket()

        if self._sock is not None:
            self._sock.settimeout(self.timeout)
            self._last_used = now
            return

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            s.connect((self.ip, self.port))
            self._sock = s
            self._last_used = now
            self.dbg("TCP connect OK")
        except Exception as e:
            self._sock = None
            raise IOError(f"TCP connect fout: {e}")

    def _close_socket(self):
        try:
            if self._sock:
                self._sock.close()
        except:
            pass
        self._sock = None

    # ---------------------------------------------------------
    # LOW-LEVEL MODBUS TCP EXCHANGE
    # ---------------------------------------------------------

    def _exchange(self, pdu: bytes) -> bytes:
        tid = random.randint(0, 65535)
        length = len(pdu) + 1
        mbap = struct.pack(">HHHB", tid, 0, length, self.unit_id)
        adu = mbap + pdu

        for attempt in range(2):
            try:
                self._ensure_socket()
                s = self._sock

                s.sendall(adu)

                header = self._recv_exact(s, 7)
                r_tid, _, r_len, _ = struct.unpack(">HHHB", header)

                if r_tid != tid:
                    raise IOError("Transaction ID mismatch")

                payload = self._recv_exact(s, r_len - 1)
                self._last_used = time.time()
                return payload

            except Exception:
                self._close_socket()
                if attempt == 1:
                    raise

    def _recv_exact(self, s: socket.socket, n: int) -> bytes:
        data = b""
        end_time = time.time() + self.timeout

        while len(data) < n:
            if time.time() > end_time:
                raise IOError("Timeout tijdens recv")

            chunk = s.recv(n - len(data))
            if not chunk:
                raise IOError("Verbinding gesloten tijdens recv")

            data += chunk

        return data

    # ---------------------------------------------------------
    # MODBUS FUNCTIONS
    # ---------------------------------------------------------

    def read_input_block(self, addr: int, count: int):
        pdu = struct.pack(">BHH", 0x04, addr, count)
        resp = self._exchange(pdu)

        if resp[0] & 0x80:
            raise IOError(f"Modbus exception {resp[1]}")

        bytecount = resp[1]
        data = resp[2:2 + bytecount]

        regs = []
        for i in range(0, bytecount, 2):
            regs.append(struct.unpack(">H", data[i:i + 2])[0])
        return regs

    def read_holding_block(self, addr: int, count: int):
        pdu = struct.pack(">BHH", 0x03, addr, count)
        resp = self._exchange(pdu)

        if resp[0] & 0x80:
            raise IOError(f"Modbus exception {resp[1]}")

        bytecount = resp[1]
        data = resp[2:2 + bytecount]

        regs = []
        for i in range(0, bytecount, 2):
            regs.append(struct.unpack(">H", data[i:i + 2])[0])
        return regs

    def read_holding_single(self, addr: int):
        return self.read_holding_block(addr, 1)[0]

    def write_holding_single(self, addr: int, value: int):
        pdu = struct.pack(">BHH", 0x06, addr, value)
        resp = self._exchange(pdu)

        if resp[0] & 0x80:
            raise IOError(f"Modbus exception {resp[1]}")

        r_addr, r_val = struct.unpack(">HH", resp[1:5])
        if r_addr != addr or r_val != value:

            raise IOError("Write echo mismatch")
