# Stundenplan Suite (Home Assistant)

![Version](https://img.shields.io/github/v/release/fabel-smith/stundenplan-suite)
![Maintenance](https://img.shields.io/maintenance/yes/2026)
![License](https://img.shields.io/github/license/fabel-smith/stundenplan-suite)

> **TL;DR**
> - **Du nutzt stundenplan24.de?** → installiere die **stundenplan-suite**
> - **Anzeige erfolgt über die stundenplan-card**

Die **stundenplan-suite** ist die **Backend-Erweiterung** zur **stundenplan-card**.  
Sie verbindet **stundenplan24.de** mit Home Assistant und stellt den Stundenplan automatisch als Sensor bereit.

➡️ **Anzeige & Visualisierung** erfolgt über die **stundenplan-card**:  
https://github.com/fabel-smith/stundenplan-card

---

## Was macht die stundenplan-suite?

Kurz gesagt:

- holt den Stundenplan automatisch von **stundenplan24.de**
- verarbeitet **A/B-Wechselwochen**
- stellt die Daten als **Home-Assistant-Sensor(en)** bereit
- kein manuelles JSON, kein REST-Sensor nötig

> **Merksatz:**  
> **Suite = Daten + Logik**  
> **Card = Anzeige**

---

## Wann brauchst du die Suite?

Du brauchst die **stundenplan-suite**, wenn du:

- deinen Stundenplan **nicht manuell pflegen** willst
- **stundenplan24.de** nutzt
- A/B-Wochen automatisch umschalten möchtest
- saubere Entities in Home Assistant haben willst

Du brauchst sie **nicht**, wenn du:
- nur eine manuelle Tabelle anzeigen möchtest → **stundenplan-card**

---

## 🔄 Wechsel von der stundenplan-card (Migration)

Du nutzt bereits die **stundenplan-card** mit manuellen Daten  
(JSON-Dateien + REST-Sensor)?

Der Umstieg auf die **stundenplan-suite** ist einfach:

### Kurzfassung
- Die Suite ersetzt **JSON + REST-Sensor**
- Die Card bleibt als Anzeige bestehen

### Schritte
1. **stundenplan-suite** über HACS installieren  
2. Home Assistant neu starten  
3. Integration konfigurieren  
4. In der Card den neuen Sensor auswählen

### Optional aufräumen
Nach erfolgreichem Umstieg kannst du:
- manuelle JSON-Dateien löschen
- REST-Sensoren entfernen

> **Wichtig:**  
> Nicht beides parallel betreiben (Suite **oder** manuell).
> Entweder stundenplan-suite ODER manuelle JSON + REST-Sensor – niemals beides gleichzeitig.


## Architektur (vereinfacht)

```
stundenplan24.de
        ↓
stundenplan-suite (Integration)
        ↓
Home Assistant Sensor
        ↓
stundenplan-card (Lovelace)
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

Folge dem Konfigurationsdialog (Zugangsdaten / Auswahl des Stundenplans).

---

## Entitäten

Die Integration erstellt automatisch einen oder mehrere Sensoren, z. B.:

- `sensor.stundenplan24_week_rows_ha`
- (Name kann je nach Konfiguration variieren)

Diese Sensoren enthalten den Stundenplan strukturiert als Attribute.

---

## Nutzung mit der stundenplan-card

In der **stundenplan-card** einfach den von der Suite erzeugten Sensor auswählen.

Beispiel:

```yaml
type: custom:stundenplan-card
entity: sensor.stundenplan24_week_rows_ha
```

> **Wichtig:**  
> Bei Nutzung der Suite **keine** eigenen JSON-Dateien und **keine** REST-Sensoren anlegen.

---

## Updates

- Änderungen an stundenplan24.de werden automatisch übernommen
- Neue Features erscheinen über normale HACS-Updates

---

## Support & Hinweise

- Änderungen an der stundenplan24-Webseite können Anpassungen erfordern  
- Bei Problemen bitte ein **GitHub Issue** erstellen (gern mit Log-Auszug)

---

<a href="https://www.buymeacoffee.com/fabelsmith" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" height="45" alt="Buy Me a Coffee">
</a>
