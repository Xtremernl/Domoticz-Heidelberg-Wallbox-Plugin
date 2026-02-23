"""
<plugin key="heidelberg-wallbox"
        name="Heidelberg Amperfied Wallbox"
        author="XtremerNL"
        version="0.9.26">
    <params>
        <param field="Address" label="IP-adres wallbox" width="200px" required="true"/>
        <param field="Port" label="Modbus TCP poort" width="100px" required="true" default="502"/>
        <param field="Mode1" label="Modbus adres" width="75px" required="true" default="1"/>
        <param field="Mode2" label="Watchdog (ms)" width="100px" required="true" default="15000"/>
        <param field="Mode3" label="Failsafe stroom (0 of 60–150)" width="140px" required="true" default="0"/>
        <param field="Mode4" label="Polling interval (sec, min=1)" width="100px" required="true" default="10"/>
        <param field="Mode6" label="Debug-modus" width="100px">
            <options>
                <option label="Aan" value="True"/>
                <option label="Uit" value="False" default="true"/>
            </options>
        </param>
    </params>
</plugin>
"""

"""State management and polling utilities."""
import Domoticz
import json
import os
import threading
import time

from wallbox import HeidelbergWallbox, CHARGING_STATE_TEXT


def dbg(msg):
    """Log debug message if debug mode is enabled."""
    if Parameters["Mode6"] == "True":
        Domoticz.Log(f"[WB DEBUG] {msg}")


# State storage (JSON file)

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(PLUGIN_DIR, "wallbox_state.json")


def load_state():
    """Load state from JSON file."""
    try:
        if not os.path.exists(STATE_FILE):
            return {}
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        Domoticz.Error(f"State load error: {e}")
        return {}


def save_state(state):
    """Save state to JSON file."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        Domoticz.Error(f"State save error: {e}")


def get_state_int(state, key, default=0):
    """Get integer value from state dict with fallback."""
    try:
        return int(state.get(key, default))
    except Exception:
        return default


def set_state(state, key, value):
    """Set state value and persist to disk."""
    state[key] = value
    save_state(state)


def safe_int_svalue(unit, default=0):
    if unit in Devices:
        raw = Devices[unit].sValue
        try:
            return int(raw)
        except Exception:
            return default
    return default


class PollThread(threading.Thread):
    """Polling thread that executes callback at regular intervals."""

    def __init__(self, interval, callback):
        super().__init__()
        self.interval = max(1, float(interval))
        self.callback = callback
        self.stop_flag = False
        self.daemon = True

    def run(self):
        """Execute callback periodically."""
        while not self.stop_flag:
            start = time.time()
            try:
                self.callback()
            except Exception as e:
                Domoticz.Error(f"Poll error: {e}")
            sleep = self.interval - (time.time() - start)
            if sleep > 0:
                time.sleep(sleep)

    def stop(self):
        """Signal thread to stop."""
        self.stop_flag = True


class BasePlugin:
    """Domoticz plugin for Heidelberg Wallbox."""
    def __init__(self):
        """Initialize plugin state."""
        self.poller = None
        self.hw = None
        self.firstPollDone = False
        self.last_update = {}
        self.error_count = 0
        self.modbus_lock = threading.Lock()
        self.last_write_time = 0


        # Slider settle state
        self.slider_last_change = 0
        self.slider_last_level = None
        self.saved_level = 0

        # Modbus register 261 state
        self.last_261_value = 0

        # Selector preset state
        self.selector_is_dynamic = True
        self.selector_preset_pending = False
        self.current_selector_level = 0
        self.preset_map = {
            10: 60,    # 6A
            20: 80,    # 8A
            30: 100,   # 10A
            40: 130,   # 13A
            50: 160,   # 16A
        }

        # Charging state
        self.last_status = 0
        self.laden_was_actief = False
        self.startup_recovery_done = False
        self.stable_counter = 0
        self.state = {}

    def updateDevice(self, unit, nValue, sValue):
        """Update device, avoiding redundant updates within 1 hour."""
        now = time.time()

        if unit not in self.last_update:
            Devices[unit].Update(nValue, sValue)
            self.last_update[unit] = (nValue, sValue, now)
            return

        last_n, last_s, last_t = self.last_update[unit]
        time_threshold = 3600  # 1 hour

        if nValue != last_n or sValue != last_s or (now - last_t) >= time_threshold:
            Devices[unit].Update(nValue, sValue)
            self.last_update[unit] = (nValue, sValue, now)

    def initVariables(self):
        """Initialize variables from persistent state."""
        self.state = load_state()

        # Load persisted values
        laden_was_actief = get_state_int(self.state, "WB_laden_was_actief", 0)
        auto_was_status = get_state_int(self.state, "WB_auto_was_status", 0)
        selector_level_var = get_state_int(self.state, "WB_selector_level", 0)
        slider_level_var = get_state_int(self.state, "WB_slider_level", 0)

        # Get device values with fallback to state
        selector_level_dev = safe_int_svalue(18, selector_level_var)
        slider_level_dev = safe_int_svalue(14, slider_level_var)

        # Initialize plugin state
        self.current_selector_level = selector_level_dev
        self.selector_is_dynamic = selector_level_dev == 0
        self.saved_level = slider_level_dev
        self.laden_was_actief = laden_was_actief == 1
        self.last_status = auto_was_status

        # Persist values
        set_state(self.state, "WB_selector_level", selector_level_dev)
        set_state(self.state, "WB_slider_level", slider_level_dev)
        set_state(self.state, "WB_laden_was_actief", 1 if self.laden_was_actief else 0)
        set_state(self.state, "WB_auto_was_status", self.last_status)

        dbg(f"Init vars: selector={self.current_selector_level}, slider={self.saved_level}, "
            f"laden_was_actief={self.laden_was_actief}, auto_was_status={self.last_status}")

    def onStart(self):
        """Start plugin and polling thread."""
        Domoticz.Log("Wallbox plugin 0.9.26 started.")

        self.ip = Parameters["Address"]
        self.port = int(Parameters["Port"])
        self.unit_id = int(Parameters["Mode1"])
        self.watchdog = int(Parameters["Mode2"])
        self.failsafe = int(Parameters["Mode3"])
        self.pollInterval = max(1, float(Parameters["Mode4"]))
        debug = Parameters["Mode6"] == "True"

        self.hw = HeidelbergWallbox(self.ip, self.port, self.unit_id, timeout=0.5, debug=debug)

        self.createDevices()
        self.initVariables()

        self.poller = PollThread(self.pollInterval, self.pollWallbox)
        self.poller.start()

    def onStop(self):
        """Stop polling thread."""
        if self.poller:
            self.poller.stop()
            self.poller.join()

    def carConnected(self):
        """Check if car is connected (states 4-8)."""
        return self.last_status in (4, 5, 6, 7, 8)

    def carDisconnected(self):
        """Check if car is disconnected (states 2-3)."""
        return self.last_status in (2, 3)

    def onCommand(self, Unit, Command, Level, Color):
        """Handle device commands."""
        dbg(f"Command: U={Unit}, C={Command}, L={Level}")

        # Remote lock
        if Unit == 13:
            self.writeRegister(259, 0 if Command == "On" else 1)
            
        # Dimmer (slider)
        elif Unit == 14:

            # UI-level bepalen
            level = 0 if Command == "Off" else int(Level)
            if level <= 2:
                level = 0

            # Pauze actief → slider mag UI aanpassen maar NIET naar 261 schrijven
            if 19 in Devices and Devices[19].nValue == 1:
                dbg("Slider genegeerd voor 261: Pauze actief")

                self.saved_level = level
                self.updateDevice(14, 1 if level > 0 else 0, str(level))
                set_state(self.state, "WB_slider_level", self.saved_level)
                return

            # Als preset actief was → slider overrult preset → terug naar dynamisch
            if not self.selector_is_dynamic:
                dbg("Slider gebruikt → preset uit, terug naar dynamisch")

                self.selector_is_dynamic = True
                self.selector_preset_pending = False
                self.current_selector_level = 0

                self.updateDevice(18, 0, "0")
                set_state(self.state, "WB_selector_level", 0)

            # Slider UI opslaan
            self.slider_last_change = time.time()
            self.slider_last_level = level
            self.saved_level = level
            set_state(self.state, "WB_slider_level", self.saved_level)

            # UI updaten
            self.updateDevice(14, 1 if level > 0 else 0, str(level))

            # Alleen naar 261 schrijven als: Laden = Aan én Pauze = Uit
            if Devices[16].nValue == 1 and Devices[19].nValue == 0:
                waarde = 60 + level if level > 0 else 60
                dbg(f"Slider → schrijf naar 261: {waarde}")
                self.writeRegister(261, waarde)
            else:
                dbg("Slider wijziging NIET naar 261 — laden uit of pauze actief")

        # Laden Aan/Uit
        elif Unit == 16:

            dbg(f"Laden commando: {Command}")

            # UI bijwerken
            if Command == "On":
                self.updateDevice(16, 1, "On")
            else:
                self.updateDevice(16, 0, "Off")

            # Laden UIT → altijd 261 = 0
            if Command == "Off":
                dbg("Laden uit → schrijf 0 naar 261")
                self.writeRegister(261, 0)
                return

            # Laden AAN → alleen schrijven als Pauze UIT staat
            if Devices[19].nValue == 0:
                level = self.saved_level
                waarde = 60 + level if level > 0 else 60
                dbg(f"Laden aan → schrijf naar 261: {waarde}")
                self.writeRegister(261, waarde)
            else:
                dbg("Laden aan maar Pauze actief → NIET naar 261 schrijven")

        # Selector (presets)
        elif Unit == 18:

            dbg(f"Selector commando: Level={Level}")

            raw_level = int(Level)  # 0,10,20,30,40,50

            # Level 0 = Dynamisch
            if raw_level == 0:
                dbg("Selector → Dynamisch gekozen")

                self.selector_is_dynamic = True
                self.selector_preset_pending = False
                self.current_selector_level = 0

                self.updateDevice(18, 0, "0")
                set_state(self.state, "WB_selector_level", 0)
                return

            # Controleer of level geldig is
            if raw_level not in self.preset_map:
                dbg(f"Selector → onbekend level {raw_level}, terug naar Dynamisch")
                self.selector_is_dynamic = True
                self.selector_preset_pending = False
                self.current_selector_level = 0
                self.updateDevice(18, 0, "0")
                set_state(self.state, "WB_selector_level", 0)
                return

            # Vanaf hier: geldige preset
            self.selector_is_dynamic = False
            self.selector_preset_pending = True
            self.current_selector_level = raw_level
            set_state(self.state, "WB_selector_level", raw_level)

            # >>> DEZE REGEL ONTBREEKT EN IS CRUCIAAL <<<
            self.updateDevice(18, raw_level, str(raw_level))

            desired_261 = self.preset_map[raw_level]
            ampere = desired_261 / 10.0

            dbg(f"Selector → preset gekozen: {ampere:.1f}A (level={raw_level}, reg261={desired_261})")

            slider_level = int((ampere - 6) * (100 / 10))
            slider_level = max(0, min(100, slider_level))

            dbg(f"Selector → slider wordt {slider_level}%")

            self.saved_level = slider_level
            self.slider_last_level = slider_level
            set_state(self.state, "WB_slider_level", slider_level)

            self.updateDevice(14, 1 if slider_level > 0 else 0, str(slider_level))

            if Devices[16].nValue == 1 and Devices[19].nValue == 0:
                dbg(f"Selector → schrijf naar 261: {desired_261}")
                self.writeRegister(261, desired_261)
            else:
                dbg("Selector wijziging NIET naar 261 — laden uit of pauze actief")

        # Pauze Aan/Uit
        elif Unit == 19:

            dbg(f"Pauze commando: {Command}")

            # UI bijwerken
            if Command == "On":
                self.updateDevice(19, 1, "On")
            else:
                self.updateDevice(19, 0, "Off")

            # Pauze AAN → altijd 261 = 0
            if Command == "On":
                dbg("Pauze aan → schrijf 0 naar 261")
                self.writeRegister(261, 0)
                return

            # Pauze UIT → alleen schrijven als Laden AAN staat
            if Devices[16].nValue == 1:
                level = self.saved_level
                waarde = 60 + level if level > 0 else 60
                dbg(f"Pauze uit → schrijf naar 261: {waarde}")
                self.writeRegister(261, waarde)
            else:
                dbg("Pauze uit maar Laden uit → NIET naar 261 schrijven")

    # ---------------- Devices ----------------

    def createDevices(self):
        devices = {
            1: ("Status", 243, 19, 0),
            2: ("Stroom L1", 243, 23, 0),
            3: ("Stroom L2", 243, 23, 0),
            4: ("Stroom L3", 243, 23, 0),
            5: ("PCB", 80, 5, 0),
            6: ("Spanning L1", 243, 8, 0),
            7: ("Spanning L2", 243, 8, 0),
            8: ("Spanning L3", 243, 8, 0),
            9: ("Ext. Verg", 244, 73, 0),
            10: ("Energie", 243, 29, 0),
            11: ("Max HW", 243, 23, 0),
            12: ("Min HW", 243, 23, 0),
            13: ("Vergrendeling", 244, 73, 0),
            14: ("Laadstroom", 244, 11, 7),
            15: ("Communicatie", 244, 73, 0),
            16: ("Laden", 244, 73, 0),
            17: ("Ingestelde laadstroom", 243, 23, 0),
            18: ("Preset laadstroom", 244, 62, 18),
            19: ("Pauze", 244, 73, 0),
        }

        for idx, (name, typ, subtype, switchtype) in devices.items():
            if idx not in Devices:
                if idx == 18:
                    Domoticz.Device(
                        Name=name,
                        Unit=idx,
                        Type=typ,
                        Subtype=subtype,
                        Switchtype=switchtype,
                        Options={
                            "LevelNames": "Dynamisch|6A|8A|10A|13A|16A",
                            "LevelOffHidden": "false",
                            "SelectorStyle": "0"
                        }
                    ).Create()
                else:
                    Domoticz.Device(Name=name, Unit=idx, Type=typ, Subtype=subtype,
                                    Switchtype=switchtype).Create()

    def _calculate_charge_current(self):
        """Calculate charge current based on selector state."""
        if self.selector_is_dynamic:
            return 60 + self.saved_level if self.saved_level > 0 else 60
        if self.current_selector_level in self.preset_map:
            self.selector_preset_pending = True
            return self.preset_map[self.current_selector_level]
        return 60

    def handleSliderSettle(self):

        # Pauze actief → slider mag niets doen
        if 19 in Devices and Devices[19].nValue == 1:
            dbg("Slider-settle genegeerd: Pauze actief")
            return

        if self.slider_last_change == 0:
            return

        if time.time() - self.slider_last_change < 5:
            return

        level = self.slider_last_level or 0

        if level <= 5:
            level = 0

        self.slider_last_change = 0
        self.slider_last_level = None

    def startupRecovery(self):
        """One-time startup recovery from persistent state."""
        dbg("StartupRecovery: begin")
        
        # Pauze actief → altijd 261 = 0, Laden‑schakelaar NIET bedienen
        if 19 in Devices and Devices[19].nValue == 1:
            dbg("StartupRecovery: Pauze actief → 261=0, Laden‑schakelaar blijft zoals hij is")
            self.writeRegister(261, 0)
            self.startup_recovery_done = True
            return

        # Stap 4: Bepaal of de auto aan het laden was (JSON)
        if not self.laden_was_actief:
            dbg("StartupRecovery: laden_was_actief == 0 → geen herstel, direct door naar normale modus")
            self.startup_recovery_done = True
            return

        # Stap 5: Is de auto nog steeds aangesloten?
        if self.carDisconnected():
            dbg("StartupRecovery: auto niet aangesloten → laden uit + 261=0")

            # Lader uit
            if Devices[16].nValue != 0:
                self.updateDevice(16, 0, "Off")

            # 261 = 0
            try:
                self.writeRegister(261, 0)
            except Exception as e:
                Domoticz.Error(f"StartupRecovery: fout bij schrijven 261=0: {e}")

            # JSON resetten
            self.laden_was_actief = False
            set_state(self.state, "WB_laden_was_actief", 0)

            self.startup_recovery_done = True
            return

        if not self.carConnected():
            dbg("StartupRecovery: status nog niet duidelijk (geen 2/3/4/5/6/7/8) → geen beslissing")
            return

        # Stap 6: Auto is aangesloten én laden_was_actief == 1 → herstellen vanuit JSON
        selector_level = get_state_int(self.state, "WB_selector_level", 0)
        slider_level = get_state_int(self.state, "WB_slider_level", 0)

        self.current_selector_level = selector_level
        self.selector_is_dynamic = (selector_level == 0)
        self.saved_level = slider_level

        if self.selector_is_dynamic:
            desired = 60 + slider_level if slider_level > 0 else 60
        else:
            desired = self.preset_map.get(selector_level, 60)

        dbg(f"StartupRecovery: auto aangesloten, JSON-herstel desired={desired}, "
            f"selector={selector_level}, slider={slider_level}")

        try:
            self.writeRegister(261, desired)
        except Exception as e:
            Domoticz.Error(f"StartupRecovery: fout bij schrijven 261={desired}: {e}")

        # UI herstellen
        level = max(0, min(100, desired - 60)) if desired >= 60 else 0
        self.saved_level = level
        self.updateDevice(14, 1 if level > 0 else 0, str(level))
        set_state(self.state, "WB_slider_level", self.saved_level)

        if self.selector_is_dynamic:
            self.updateDevice(18, 0, "0")
            set_state(self.state, "WB_selector_level", 0)
        else:
            self.updateDevice(18, 1 if self.current_selector_level > 0 else 0,
                              str(self.current_selector_level))
            set_state(self.state, "WB_selector_level", self.current_selector_level)

        self.updateDevice(16, 1, "On")
        self.laden_was_actief = True
        set_state(self.state, "WB_laden_was_actief", 1)

        self.startup_recovery_done = True
        dbg("StartupRecovery: klaar, daarna geen automatische ingrepen meer")

    def pollWallbox(self):
        """Poll wallbox and update devices."""
        try:
            with self.modbus_lock:
                regs = self.hw.read_input_block(5, 10)

            status = regs[0]
            self.last_status = status
            set_state(self.state, "WB_auto_was_status", status)

            self.laden_was_actief = (get_state_int(self.state, "WB_laden_was_actief", 0) == 1)

            if not self.firstPollDone:
                self.firstPollDone = True
                self.writeRegister(257, self.watchdog)
                self.writeRegister(262, self.failsafe)

            self.error_count = 0

            # Status device
            self.updateDevice(1, 0, CHARGING_STATE_TEXT.get(status, "Onbekend"))

            # Current L1-3 (divide by 10)
            for i, idx in enumerate([2, 3, 4]):
                self.updateDevice(idx, 0, f"{regs[1 + i] / 10:.1f}")

            # PCB temp (divide by 10)
            self.updateDevice(5, 0, f"{regs[4] / 10:.1f}")

            # Voltage L1-3
            for i, idx in enumerate([6, 7, 8]):
                self.updateDevice(idx, 0, str(regs[5 + i]))

            # External lock
            try:
                with self.modbus_lock:
                    val_13 = self.hw.read_input_block(13, 1)[0]

                locked = val_13 == 0
                self.updateDevice(9, 1 if locked else 0,
                                  "Locked" if locked else "Released")
            except Exception:
                pass

            # Remote lock (register 259)
            try:
                with self.modbus_lock:
                    val_259 = self.hw.read_holding_single(259)

                locked = val_259 == 0
                self.updateDevice(13, 1 if locked else 0,
                                  "On" if locked else "Off")
            except Exception:
                pass

            # Energy and power
            with self.modbus_lock:
                regs2 = self.hw.read_input_block(17, 2)

            energy = (regs2[0] << 16) + regs2[1]
            power = regs[9]

            dbg(f"Energy: regs2={regs2}, Wh={energy}")
            self.updateDevice(10, 0, f"{power};{energy:.3f}")

            # Max/min HW current
            with self.modbus_lock:
                regs3 = self.hw.read_input_block(100, 2)

            self.updateDevice(11, 0, str(regs3[0]))
            self.updateDevice(12, 0, str(regs3[1]))

            # Register 261 (for UI/sync only)
            with self.modbus_lock:
                val_261 = self.hw.read_holding_single(261)

            self.last_261_value = val_261

            # Stable status counter for startup recovery
            if status in (2, 3, 4, 5, 6, 7, 8):
                self.stable_counter += 1
            else:
                self.stable_counter = 0

            # One-time startup recovery after stable data
            if not self.startup_recovery_done and self.stable_counter >= 2:
                dbg("StartupRecovery: stable data available, executing recovery")
                self.startupRecovery()
            elif not self.startup_recovery_done:
                dbg("StartupRecovery: waiting for stable data")

            # Set charge current display (from register 261)
            inst_amp = val_261 / 10.0
            self.updateDevice(17, 0, f"{inst_amp:.1f}")

            pauze_actief = (19 in Devices and Devices[19].nValue == 1)

            # Pauze actief → 261 moet 0 zijn, maar Wallbox - Laden NIET bedienen
            if pauze_actief:
                if val_261 != 0:
                    self.writeRegister(261, 0)
                # Geen updateDevice(16, ...) hier: Pauze mag Laden niet sturen

            # Communication OK
            self.updateDevice(15, 1, "On")

            # Dimmer-settle
            self.handleSliderSettle()

        except Exception as e:
            Domoticz.Error(f"Poll-fout: {e}")
            self.error_count += 1
            self.updateDevice(15, 0, "Off")

            if self.error_count >= 3:
                try:
                    self.hw._close_socket()
                except Exception:
                    pass
                self.error_count = 0

    def writeRegister(self, reg, value):
        """Write value to Modbus holding register with lock + debounce."""
        try:
            with self.modbus_lock:
                now = time.time()

                # Debounce: minimaal 150ms tussen writes
                if now - self.last_write_time < 0.15:
                    time.sleep(0.15 - (now - self.last_write_time))

                self.last_write_time = time.time()

                self.hw.write_holding_single(reg, value)

        except Exception as e:
            Domoticz.Error(f"Write error reg {reg}: {e}")
            try:
                self.hw._close_socket()
            except:
                pass



global _plugin
_plugin = BasePlugin()


def onStart():
    _plugin.onStart()


def onStop():
    _plugin.onStop()


def onCommand(Unit, Command, Level, Color):
    _plugin.onCommand(Unit, Command, Level, Color)


def onHeartbeat():
    """Domoticz heartbeat callback (unused)."""
    pass

