# Stundenplan Suite (Home Assistant)

Eine Home-Assistant **Custom Integration + Lovelace Card** zur Anzeige von Stundenplänen  
inkl. **A/B-Wochen**, **aktueller Stunde**, **Pausen**, **Vertretungen** und **visuellem Editor**.

Die Suite besteht aus:
- einer **Integration** (`stundenplan24_week`)
- einer **Custom Lovelace Card** (`stundenplan-card`)

Optimiert für **HACS**.

---

## ✨ Features

### Integration
- Stundenplan als Sensor in Home Assistant
- Unterstützung für:
  - Wochenpläne (A/B)
  - Tages- und Wochenwechsel
  - Vertretungsdaten (WPlan)
- Liefert strukturierte Daten für die Lovelace Card (`rows_ha`)
- Vollständig lokal, kein Cloud-Zwang

### Lovelace Card
- Tabellarischer Stundenplan
- Visueller Editor direkt in Home Assistant
- Highlights:
  - heutiger Tag
  - aktuelle Stunde
  - optionale Pausen-Hervorhebung
- Freistunden-Logik (kein „Aktuell“-Highlight bei leeren Zellen)
- Farben & Zell-Styles konfigurierbar
- Funktioniert mit:
  - Integration (empfohlen)
  - beliebigen JSON-Entities
  - manuellen Einträgen

---

## 📦 Installation (HACS)

### 1. Custom Repository hinzufügen
HACS → **Integrations** → **Custom repositories**

- Repository:  
