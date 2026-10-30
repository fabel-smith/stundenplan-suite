# Schulmanager mit Kursauswahl

In der Vorabversion **v0.4.0b1** ist die direkte Anbindung optional verfügbar. Voraussetzung
ist die Aktion `schulmanager.get_schedule` der Integration von MrIcemanLE.
Getestet wurde **Schulmanager Online v0.13.0b4**, noch eine Vorabversion.
Die bisherige Kalender-/Sensor-Anbindung funktioniert weiterhin und wird nicht
automatisch umgestellt.

## Bestehende Einrichtung umstellen

1. Schulmanager Online auf die passende Version aktualisieren und HA neu starten.
2. Einstellungen → Geräte & Dienste → Stundenplan Suite → Konfigurieren öffnen.
3. **Neue Schulmanager-Schnittstelle verwenden** einschalten.
4. Das richtige Kind und Konto auswählen.
5. Nur Kurse markieren, an denen das Kind **nicht** teilnimmt. Leer lässt alle sichtbar.

Die Auswahl verwendet Kurskennungen, keine Fachnamen oder Räume. Dadurch können
zwei gleichnamige Parallelkurse getrennt behandelt werden. Welche Gruppe das Kind
besucht, muss weiterhin bekannt sein; die Suite rät diese Zuordnung nicht.
Neue Kurse bleiben sichtbar. Gespeicherte Ausschlüsse bleiben auch über Ferien erhalten.
Sonderstunden ohne Kurskennung werden vorsichtshalber nicht ausgeblendet.

Entity-IDs und Wochenauswahl bleiben beim Umstellen erhalten. Zum Zurückwechseln
den Schalter ausschalten und die bisherigen Kalender-/Sensorquellen bestätigen.
Bei neu angelegten Einträgen müssen diese Quellen dann erst ausgewählt werden.

## Anzeige in der Karte

Card **v3.11.0-beta.1** zeigt unter **Inhalte filtern** die bereits durch die Suite
ausgeblendeten Kurse schreibgeschützt an. Zusätzliche Kartenfilter gelten nur für
die einzelne Karte; Suite-Filter gelten für alle Anzeigen derselben Suite-Quelle.

Bei einem tatsächlichen Fachwechsel zeigt die Karte **Bisher** und **Jetzt**
nebeneinander. Reine Raum-/Lehrerwechsel bleiben kompakt. Fehlende oder
uneindeutige Originaldaten führen nicht zu einem geratenen Vergleich.
Mehrere Räume desselben Kurses bleiben erhalten; andere Kurse bleiben getrennt.

## Daten und Grenzen

Die Suite liest den vorhandenen Datenbestand der Schulmanager-Integration und
erzeugt damit keine zusätzlichen Anfragen an die Schule. Geladene leere Tage,
nicht geladene Zeiträume und veraltete/nicht verfügbare Quellen werden unterschieden.
Die Tages-Sensoren bleiben unabhängig von der gerade angezeigten Woche.
Bei unbekannten oder uneindeutigen Daten werden Schulroutinen nicht als sicher bestätigt.

Getestet wurden der HA-Betrieb mit echten Kursfiltern sowie nachgebildete
Fachwechsel und Mehrraumfälle. Die Rückmeldung zu den besonderen Parallelkursen
anderer Schulen bleibt wichtig; bitte solche Fälle nach dem Umstieg prüfen.

Technisch enthält `rows_table` bei Fachwechseln optional `subject_changes` mit
Wochentag sowie `current` und `original` als Zelltext. Das ist nur eine
Darstellungsergänzung, keine zweite Unterrichtsstunde. Ältere Karten ignorieren sie.
