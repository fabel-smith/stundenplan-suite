# Stundenplan Suite (Home Assistant)

![Version](https://img.shields.io/github/v/release/fabel-smith/stundenplan-suite)
![Maintenance](https://img.shields.io/maintenance/yes/2026)
![License](https://img.shields.io/github/license/fabel-smith/stundenplan-suite)

> **TL;DR**
> - **Du nutzt stundenplan24.de?** → installiere die **stundenplan-suite**
> - **Du nutzt Schulmanager Online?** → verbinde die vorhandene Schulmanager-Integration mit der **stundenplan-suite**
> - **Anzeige erfolgt über die stundenplan-card**

Die **stundenplan-suite** ist die **Backend-Erweiterung** zur **stundenplan-card**.  
Sie verbindet **stundenplan24.de** oder die benutzerdefinierte Home-Assistant-Integration
**Schulmanager Online** mit der Karte und stellt den Stundenplan in einem einheitlichen
Sensorformat bereit.

➡️ **Anzeige & Visualisierung** erfolgt über die **stundenplan-card**:  
https://github.com/fabel-smith/stundenplan-card

---

## Was macht die stundenplan-suite?

Kurz gesagt:

- holt den Stundenplan automatisch von **stundenplan24.de** oder übernimmt ihn aus **Schulmanager Online**
- verarbeitet **A/B-Wechselwochen**
- stellt die Daten als **Home-Assistant-Sensor(en)** bereit
- kein manuelles JSON, kein REST-Sensor nötig
- rekonstruiert bei Schulmanager fehlende Pausenzeilen aus dem Stundenraster
- markiert Ausfälle und geänderte Stunden farblich in der stundenplan-card

> **Merksatz:**  
> **Suite = Daten + Logik**  
> **Card = Anzeige + manueller Editor**

---

## Wann brauchst du die Suite?

Die **stundenplan-suite** übernimmt die automatische Datenaufbereitung für die
Karte, wenn du **stundenplan24.de** oder eine vorhandene
**Schulmanager-Online-Integration** als Quelle verwenden möchtest.

Du brauchst sie **nicht**, wenn du deinen Plan im Karteneditor manuell pflegst
oder bereits einen passenden JSON-Sensor hast. **Manuelle A/B-Wechselwochen**
mit automatischer Umschaltung nach Kalenderwoche unterstützt die Karte selbst.

---

## Wechsel von manuellen Daten zur automatischen Quelle

Du nutzt die **stundenplan-card** mit manuell eingetragenen Stunden oder einem
eigenen JSON-/REST-Sensor und möchtest künftig Daten aus **Stundenplan24** oder
**Schulmanager Online** übernehmen? Die Karte bleibt dabei erhalten.

### Kurzfassung
- Die Suite bereitet die Daten einer unterstützten Quelle als Wochensensor auf
- Die Card bleibt als Anzeige bestehen
- Vorhandene manuelle Pläne oder JSON-Dateien werden nicht in die Suite importiert

### Schritte
1. **stundenplan-suite** über HACS installieren  
2. Home Assistant neu starten  
3. Die gewünschte Quelle konfigurieren; bei Schulmanager muss dessen Integration bereits eingerichtet sein
4. In der Card unter **Datenquellen → Stundenplan Suite (Integration)** den neuen Wochensensor auswählen

### Optional aufräumen
Nach erfolgreichem Umstieg kannst du nicht mehr benötigte JSON-Dateien oder
REST-Sensoren entfernen. Prüfe vorher, ob andere Karten oder Automationen sie
noch verwenden, und sichere deine bisherige Konfiguration.

> **Wichtig:**  
> Jede Karte verwendet die dort ausgewählte Datenquelle. Mehrere Karten mit
> unterschiedlichen Quellen können problemlos nebeneinander genutzt werden,
> beispielsweise ein manueller Plan für ein Kind und ein Suite-Plan für ein anderes.


## Architektur (vereinfacht)

```text
stundenplan24.de ───────────────────────────────┐
                                               ├─> stundenplan-suite
Schulmanager Online Integration ─> HA-Entities ┘          ↓
                                                  Home-Assistant-Sensor
                                                           ↓
                                                  stundenplan-card
```

---

## Installation (HACS)

### 1) Repository zu HACS hinzufügen

HACS → **Integrationen** → **⋮** → *Benutzerdefiniertes Repository*

- Repository:  
  `https://github.com/fabel-smith/stundenplan-suite`
- Kategorie: **Integration**

Danach die **stundenplan-suite** installieren.

---

### 2) Home Assistant neu starten

Nach der Installation **Home Assistant neu starten**.

---

### 3) Integration hinzufügen

Einstellungen → **Geräte & Dienste** → **Integration hinzufügen** → **Stundenplan Suite**

Wähle anschließend die gewünschte Quelle:

#### Stundenplan24

Gib die Zugangsdaten und den gewünschten Stundenplan im Konfigurationsdialog an.

#### Schulmanager Online

Voraussetzung ist die installierte benutzerdefinierte Integration
[Schulmanager Online](https://github.com/rwunsch/schulmanager-online-hass).
Die Suite benötigt keine zusätzlichen Schulmanager-Zugangsdaten, sondern liest die
bereits in Home Assistant vorhandenen Entitäten.

Wähle für dasselbe Kind:

- den Stundenplankalender,
- die Sensoren für heute und morgen,
- den Wochen-Sensor,
- optional den Änderungssensor.

Verwende den Stundenplankalender des Kindes, nicht den allgemeinen Schulkalender.
Die Suite erzeugt daraus einen eigenen `*_woche`-Sensor für die Karte. Pausen, die
im Kalender fehlen, werden aus dem Stundenraster ergänzt. Neben ausdrücklich als
Pause bezeichneten Zeilen erkennt die Suite auch Lücken ab 10 Minuten zwischen
zwei Unterrichtszeiten. Kürzere Wechselzeiten werden nicht als Pause angezeigt.

Vom Schulmanager gemeldete Ausfälle und Änderungen werden als strukturierte
`cell_styles` an die Karte übergeben. Ausfälle erscheinen rot, Änderungen gelb.
Normale Unterrichtsstunden erhalten keinen zusätzlichen Stil. Bei mehreren
Einträgen in derselben Zelle hat ein Ausfall Vorrang vor einer Änderung.

---

## Entitäten

Die Integration erstellt unabhängig von der gewählten Quelle einen oder mehrere Sensoren, z. B.:

- `sensor.stundenplan24_week_rows_ha`
- (Name kann je nach Konfiguration variieren)

Diese Sensoren enthalten den Stundenplan strukturiert als Attribute.

---

## Nutzung mit der stundenplan-card

In der **stundenplan-card** unter **Datenquellen → Stundenplan Suite (Integration)**
einfach den von der Suite erzeugten Wochensensor auswählen. Das funktioniert sowohl
mit Stundenplan24 als auch mit Schulmanager Online.

Beispiel:

```yaml
type: custom:stundenplan-card
source_type: entity
source_entity: sensor.stundenplan24_week_rows_ha
```

Ersetze die Beispiel-Entity durch den tatsächlichen Wochensensor deiner Suite.

> **Wichtig:**  
> Für die Suite-Anbindung sind **keine** zusätzlichen JSON-Dateien oder
> REST-Sensoren erforderlich. Unabhängige JSON-/REST-basierte Karten kannst du weiter nutzen.

### JSON-Vertrag für Zellfarben

Die Karte akzeptiert Farben unabhängig von der Datenquelle über das optionale
Array `cell_styles`. Jeder Eintrag entspricht dem Tag an derselben Position in
`cells`:

```json
{
  "time": "2.",
  "cells": ["D", "M", "Entfällt: E", "", "Sp"],
  "cell_styles": [null, null, {
    "bg": "#d32f2f",
    "bg_alpha": 0.2,
    "color": "var(--error-color, #ff5252)"
  }, null, null]
}
```

Die Suite erzeugt diese Angaben für unterstützte Statusinformationen automatisch.

---

## Updates

- Änderungen der konfigurierten Datenquelle werden automatisch übernommen
- Neue Features erscheinen über normale HACS-Updates

---

## Support & Hinweise

- Änderungen an Stundenplan24 oder an der inoffiziellen Schulmanager-Schnittstelle können Anpassungen erfordern
- Bei Problemen bitte ein **GitHub Issue** erstellen (gern mit Log-Auszug)

---

<a href="https://www.buymeacoffee.com/fabelsmith" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" height="45" alt="Buy Me a Coffee">
</a>
