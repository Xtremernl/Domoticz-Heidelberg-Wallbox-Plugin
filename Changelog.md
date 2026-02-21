CHANGELOG — Heidelberg Amperfied Wallbox Domoticz Plugin
Auteur: Xtremernl

0.9.25 – interne stabiliteitsrelease
• 	Volledige herbouw van de laadlogica: UI‑leidend, geen poll‑interferentie.
• 	Verbeterde selector/slider‑consistentie en correcte UI‑feedback.
• 	Deterministische 261‑aansturing en stabiele startupRecovery.
• 	Geen wijzigingen aan de gebruikersinterface of installatieprocedure.

Versie 0.9.24
- Fix: Pauze‑schakelaar beïnvloedde onterecht de “Wallbox – Laden” schakelaar

Versie 0.9.23
- Fix: wijzigen van een preset (selector) zet de laadpaal niet langer automatisch aan.
- Verbetering: als de slider wordt gebruikt terwijl een preset actief was, schakelt de plugin automatisch terug naar dynamisch laden.
- Verbetering: tijdens pauze wordt de slider-UI niet meer overschreven door register 261.
- Verbetering: selector‑ en slider‑sync verder verfijnd.
- Verbetering: robuustere state‑opslag en herstelgedrag.
- Kleine optimalisaties en code‑cleanup.

Versie 0.9.22
- Toegevoegd: slider‑wijziging forceert terug naar dynamisch laden wanneer een preset actief was.
- Verbetering: pauze‑modus blokkeert nu correct alle preset‑ en slider‑acties richting register 261.
- Verbetering: UI‑sync van slider wordt overgeslagen tijdens pauze.
- Verbetering: selector‑sync verbeterd.
- Diverse stabiliteitsverbeteringen.

Versie 0.9.21
- Verbetering: selector‑ en slider‑logica verder opgeschoond.
- Verbetering: pauze‑modus uitgebreid en betrouwbaarder gemaakt.
- Verbetering: state‑herstel verbeterd.
- Kleine bugfixes.

Versie 0.9.20
- Grote update: volledige herstructurering van startup‑recovery.
- Nieuw: laden_was_actief wordt opgeslagen en gebruikt voor herstel na Domoticz‑restart.
- Nieuw: stabiele‑status‑teller om te voorkomen dat verkeerde beslissingen worden genomen voordat de wallbox consistente data levert.
- Verbetering: selector‑sync en preset‑pending logica verbeterd.
- Verbetering: slider‑settle logica verfijnd.
- Verbetering: pauze‑modus toegevoegd (Unit 19).
- Verbetering: UI‑sync van slider en selector volledig herschreven.
- Diverse bugfixes en stabiliteitsverbeteringen.

Versie 0.9.14
- Code cleanup.
- Geen functionele wijzigingen.

Versie 0.9.13
- Verbetering: selector‑ en slider‑sync volledig herschreven.
- Nieuw: startup‑recovery op basis van JSON‑state.
- Nieuw: stabiele‑status‑teller voor veilig herstel.
- Verbetering: laden_was_actief wordt nu correct opgeslagen en hersteld.
- Verbetering: UI‑sync van selector en slider verbeterd.
- Diverse bugfixes.

Versie 0.9.11
- Toegevoegd: lokale JSON‑state voor selector, slider, status en laden_was_actief.
- Nieuw: herstel na Domoticz‑restart op basis van opgeslagen state.
- Verbetering: selector‑preset‑pending logica.
- Verbetering: slider‑settle logica.
- Verbetering: robuustere Modbus‑foutafhandeling.
- Diverse verbeteringen en fixes.

Versie 0.9.10
- Eerste stabiele versie met volledige Modbus‑implementatie.
- Toegevoegd: selector presets (6A, 8A, 10A, 13A, 16A).
- Toegevoegd: dynamische slider‑modus.
- Toegevoegd: laden aan/uit via register 261.
- Toegevoegd: remote lock (259).
- Toegevoegd: uitlezen van status, stromen, spanningen, temperatuur, energie en vermogen.
- Toegevoegd: slider‑settle logica.
- Basis‑UI‑sync voor selector en slider.
