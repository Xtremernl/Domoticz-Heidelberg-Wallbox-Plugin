# Heidelberg Amperfied Wallbox — Domoticz Plugin
Versie 0.9.23

Beschrijving
Deze Domoticz‑plugin integreert de HEIDELBERG Amperfied Wallbox Energy Control (firmware v1.0.8) met Domoticz.
De plugin gebruikt een eigen snelle Modbus‑TCP client (dus geen pymodbus nodig) en leest uitsluitend bewezen registers om stabiliteit te garanderen.
De plugin ondersteunt:
- uitlezen van status, stromen, spanningen, temperatuur, vermogen en energie
- instellen van laadstroom via slider of presets
- laden aan/uit
- pauze‑functie (override)
- vergrendeling
- automatische synchronisatie met register 261
- robuuste startup‑herstelprocedure
- veilige Modbus‑communicatie zonder logspam

Vereisten
- Domoticz 2022.2 of nieuwer
- Python 3.7.3
- Geen externe Modbus‑libraries nodig

Installatie
Maak de map:
Code:
mkdir -p /home/pi/domoticz/plugins/Wallbox
Plaats bestanden:
/home/pi/domoticz/plugins/Wallbox/plugin.py
/home/pi/domoticz/plugins/Wallbox/wallbox.py

Optioneel: icon‑sets in dezelfde map:
wallbox icons.zip → setnaam wallbox
wallbox lock-unlock.zip → setnaam wallbox-lock
wallbox on-off.zip → setnaam wallbox-switch

Herstart Domoticz:
Code:
sudo systemctl restart domoticz
Ga naar Domoticz → Instellingen → Hardware → Python Plugin → Heidelberg Amperfied Wallbox.

Plugin‑instellingen
IP-adres: IP van de wallbox
Modbus TCP poort: standaard 502
Modbus adres: standaard 1
Watchdog (ms): 0=uit, anders tijd in milliseconden
Failsafe stroom: 0 of 60–160 (0.1A stappen)
Polling interval: minimaal 1 seconde
Debug-modus: extra logging

Aangemaakte devices (v0.9.23)
Unit 1: Status (tekst, status 2–11)
Unit 2–4: Stroom L1–L3 (0.1A)
Unit 5: PCB temperatuur (0.1°C)
Unit 6–8: Spanning L1–L3 (Volt)
Unit 9: Externe vergrendeling (0=Locked / 1=Released)
Unit 10: Vermogen + Energie (W + kWh)
Unit 11: Max HW stroom
Unit 12: Min HW stroom
Unit 13: Afstandsvergrendeling (reg 259)
Unit 14: Laadstroom slider (0–100% → 60–160)
Unit 15: Communicatie (On/Off)
Unit 16: Laden (Aan/Uit)
Unit 17: Ingestelde laadstroom (261/10)
Unit 18: Preset laadstroom (Dynamisch / 6A / 8A / 10A / 13A / 16A)
Unit 19: Pauze (override: 261=0, laden blijft aan)

Belangrijke registers
257: Watchdog
258: Standby (0=Aan / 4=Uit)
259: Remote lock (0=On / 1=Off)
261: Laadstroom setpoint (0 of 60–160)
262: Failsafe
5–14: Status, stromen, temp, spanningen, vermogen
17–18: Energie (32‑bit)
100–101: Max/min HW stroom

Laadstroom‑logica (v0.9.23)
- Laden aan/uit (Unit 16)
Uit → schrijf 0 naar register 261
Aan → schrijf 60 + slider of presetwaarde
- Slider (Unit 14)
0–100% → 60–160 (6A–16A)
Slider verandert altijd de laadstroom als laden aan staat
Slider verandert alleen UI als laden uit staat
Slider schakelt automatisch preset uit → terug naar Dynamisch
- Presets (Unit 18)
6A → 60
8A → 80
10A → 100
13A → 130
16A → 160
Preset schrijft alleen naar 261 als laden aan staat
Preset verandert slider‑UI altijd
- Pauze (Unit 19)
Pauze forceert 261 = 0
Laden (Unit 16) blijft AAN
Slider en presets blijven UI‑matig werken maar schrijven niets
Bij Pauze uit → laadstroom wordt hersteld

Synchronisatie en UI‑gedrag
261 wordt elke poll gelezen
Slider en preset worden gesynchroniseerd
Tijdens Pauze wordt slider‑UI niet overschreven
Laden (Unit 16) volgt 261, behalve tijdens Pauze
Communicatie (Unit 15) toont Modbus‑status

Startup‑herstel (v0.9.23)
Bij opstart:
- Wallbox registers worden gelezen
- Watchdog en failsafe worden gezet
- Als Pauze actief is → altijd 261=0 + Laden=On
- Als laden actief was → laadstroom wordt hersteld
- UI wordt gesynchroniseerd
- Daarna worden geen automatische beslissingen meer genomen

Veilig Modbus‑gedrag
De plugin gebruikt een eigen Modbus‑TCP client
Leest alleen bewezen registers
Gebruikt kleine blokken om fouten te voorkomen
Herstelt socket automatisch
Voorkomt logspam
Schrijft nooit buiten 0 of 60–160

Troubleshooting
Geen devices → plugin niet geladen → herstart Domoticz
Geen verbinding → IP/poort fout → test met telnet <ip> 502
Illegal data address → te grote Modbus‑read → plugin gebruikt veilige blokken
Slider springt naar 0 → Pauze actief → correct gedrag
Preset start laden → Laden stond aan → correct gedrag

Wat is nieuw in v0.9.23
Toegevoegd: Pauze (Unit 19)
Pauze override: 261=0, Laden blijft aan
Slider‑UI blijft staan tijdens Pauze
Slider schakelt preset automatisch uit
Preset schrijft alleen naar 261 als laden aan staat
Volledig herschreven UI‑sync
Verbeterde startupRecovery
Verbeterde state‑consistentie
Geen externe Modbus‑libraries meer nodig
Geen automatisering in de plugin (alles in Domoticz scripts)
