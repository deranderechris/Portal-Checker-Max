# Portal Checker PRO MAX
Prueft IPTV-Portale auf Erreichbarkeit und erkennt Portal-Typen (Xtream Codes / Stalker). Optional koennen Credentials genutzt werden, um zu pruefen, ob tatsaechlich Kanaele abrufbar sind.

## Voraussetzungen
- Python 3.10 oder neuer
- Internetzugang

Die benoetigten Python-Pakete stehen in [requirements.txt](requirements.txt).

## Installation
1) Repository herunterladen oder klonen.
2) Abhaengigkeiten installieren:
```bash
pip install -r requirements.txt
```

## Start
Unter Windows einfach [start.bat](start.bat) ausfuehren. Alternativ:
```bash
python checker.py
```

## Eingaben
Das Tool kann URLs einzeln, als Liste oder aus Datei laden.

### Datei: eingabe/portale.txt
Eine URL pro Zeile, zum Beispiel:
```txt
http://example.com:8080
https://portal.example.net
```

### Optional: Credentials (fuer Kanal-Checks)
Ohne Zugangsdaten kann nicht sicher geprueft werden, ob ein Portal wirklich Kanaele liefert. Du kannst optional eine Datei anlegen:

Datei: eingabe/credentials.txt
```txt
# Xtream
xtream|http://host:port|user|pass
# Stalker (MAC)
stalker|http://host:port|00:1A:79:AA:BB:CC

# Kurzformen
http://host:port|user|pass
http://host:port|00:1A:79:AA:BB:CC
```

## Was wird geprueft
- Basis-Checks per Requests mit unterschiedlichen User-Agents
- Optional Proxy-Check
- Optional Selenium/Headless-Browser
- Portal-Erkennung:
	- Xtream: player_api.php, get.php, xmltv.php
	- Stalker: portal.php, /c/, /stalker_portal/
- Optionaler Kanal-Check (wenn Credentials vorhanden)

## Ausgabe
Alle Reports liegen im Ordner `ausgabe/` und sind als TXT gespeichert.

- `ausgabe/combined/` enthaelt den Gesamtreport je Portal
- `ausgabe/requests/`, `ausgabe/browser/`, `ausgabe/proxy/`, `ausgabe/headless/`, `ausgabe/session/` enthaelt Detailreports

## Bedienung
Nach Start erscheint ein Menue:
- Schnellscan: bricht ab, sobald ein Modus das Portal als online erkennt
- Vollscan: fuehrt alle Modi aus
- Profi-Modus: manuelle Tests, Pfad-Scan, Header/HTML-Analyse

## Proxy (optional)
Wenn du Proxys nutzen willst, lege eine Datei `proxies.txt` an (eine Zeile pro Proxy):
```txt
ip:port
user:pass@ip:port
```

## Fehlerbehebung
- Selenium-Probleme: Browser-Installationen pruefen, ggf. Edge/Firefox verwenden
- Keine Ausgabe: pruefe `ausgabe/` Rechte und ob URLs erreichbar sind
- Portal erkannt, aber keine Kanaele: Credentials fehlen oder sind falsch

## Rechtlicher Hinweis
Das Tool ist fuer legale Tests gedacht. Nutze es nur fuer Systeme, fuer die du eine ausdrueckliche Berechtigung hast.
