# Suite v0.4.0b1 - Vorabversion

**Vorabversion nur für freiwillige Tests. Bitte vorher ein HA-Backup erstellen.**
Testkombination: Suite **v0.4.0b1**, Card **v3.11.0-beta.1** und
Schulmanager Online **v0.13.0b4**. Noch kein reguläres Update.

## Schulmanager: Kind und Kurse auswählen

Die neue, optionale Schulmanager-Anbindung übernimmt strukturierte Stundenplandaten
direkt aus der vorhandenen Integration. In der Suite lassen sich das Kind und
anschließend nicht benötigte Kurse auswählen. Parallelkurse werden anhand ihrer
Kurskennung unterschieden, nicht anhand gleicher Fachnamen oder Räume.

**Voraussetzung für diese neue Anbindung:** Schulmanager Online mit
`schulmanager.get_schedule`, getestet mit **v0.13.0b4**. Diese Version ist noch
eine Vorabversion. Bestehende Kalender-/Sensor-Einrichtungen bleiben unverändert;
die Umstellung erfolgt nur auf Wunsch in den Suite-Einstellungen.

Mit **Stundenplan Card v3.11.0-beta.1** werden die durch die Suite ausgeblendeten Kurse
im Karteneditor erklärt. Bei tatsächlichen Fachwechseln zeigt die Karte
ursprünglichen und neuen Unterricht nebeneinander. Mehrere Räume desselben
Kurses bleiben erhalten. Die Suite kann eine unbekannte Gruppenzugehörigkeit
des Kindes nicht selbst ermitteln.

## Home Assistant startet unabhängig vom Stundenplanabruf

Stundenplan24 lädt den ersten Plan nun im Hintergrund, ohne die Einrichtung
der Suite bis zum Ende aller Netzwerkanfragen aufzuhalten. Doppelte Abfragen
derselben optionalen Zusatzpläne innerhalb einer Aktualisierung entfallen.
Bei einem fehlgeschlagenen Erstabruf wird mit zunehmendem Abstand erneut versucht.
Die Schutzpausen und Abrufbegrenzungen bleiben bestehen.

Bis Daten vorliegen, bleiben die betroffenen Sensoren nicht verfügbar. Ein
fehlgeschlagener Abruf wird nicht als unterrichtsfreier Tag ausgegeben.
Nach dem HA-Neustart wurden die Wochenpläne und der Schulmanager-Testplan geprüft;
die zuvor beobachtete Suite-Wartewarnung trat dabei nicht mehr auf. Eine feste
Verkürzung der gesamten HA-Startzeit wird nicht zugesichert.

## Update

Nach dem Suite-Update über HACS **Home Assistant neu starten**. Für die neue
Darstellung zusätzlich die Karte aktualisieren und das Dashboard vollständig
neu laden. Einstellungen und Entity-IDs bleiben erhalten.

[Schulmanager einrichten](https://github.com/fabel-smith/stundenplan-suite/blob/v0.4.0b1/SCHULMANAGER_SCHEDULE.md) ·
[Kurze Testanleitung und Rückweg](https://github.com/fabel-smith/stundenplan-suite/blob/v0.4.0b1/PRERELEASE_TEST.md) ·
[Passende Card v3.11.0-beta.1](https://github.com/fabel-smith/stundenplan-card/releases/tag/v3.11.0-beta.1)

Danke an @MrIcemanLE für die neue Schnittstelle und an @heilbreitenbach für die Beispiele!
