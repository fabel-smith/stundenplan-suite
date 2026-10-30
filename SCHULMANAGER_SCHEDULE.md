# Schulmanager mit Kursauswahl

In der Vorabversion **v0.4.0b2** ist die direkte Anbindung optional verfügbar. Voraussetzung
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

## Wochentagsfilter (ab v0.4.0b2)

Zusaetzlich zum bisherigen Ausschluss ganzer Kurse gibt es
zwei Auswahllisten: **An allen Tagen ausblenden** und **Nur an bestimmten
Wochentagen ausblenden**. Einen Kurs nur in einer der beiden Listen auswaehlen.
Fuer die zweite Liste folgt je Kurs eine Auswahl der Wochentage.

Beispiel Kunst: Den Kunstkurs nur in der Wochentagsliste auswaehlen, danach
**Montag** markieren und speichern. Kunst verschwindet montags, bleibt aber
dienstags erhalten. Bestehende Ausschluesse gelten weiterhin an allen Tagen.
Zum Entfernen einer Tagesregel den Kurs aus der Wochentagsliste entfernen.
Die Regeln bleiben auch ohne geladene Stunden gespeichert. Beim Wechsel des
Kindes oder Kontos werden beide Arten von Kursfiltern zurueckgesetzt.

Die Karte erhaelt die Tagesbeschraenkung im angezeigten Kursnamen, zum Beispiel
**nur Montag**. Es ist kein zusaetzlicher Kartenfilter erforderlich.

Kurzer Praxistest nach Installation der Vorabversion:

1. Einen Kurs mit Unterricht an mindestens zwei Tagen nur montags ausblenden.
2. Pruefen, dass andere Tage und andere Parallelkurse unveraendert bleiben.
3. Einstellungen erneut oeffnen: Kurs und Montag muessen vorausgewaehlt sein.
4. HA neu starten und Wochen wechseln: Die Regel muss erhalten bleiben.
5. Regel entfernen: Der Kurs muss wieder an allen geladenen Tagen erscheinen.

Technisch wird `excluded_course_weekdays` als Zuordnung von Kurskennung zu
Wochentagen (`mon` bis `sun`) gespeichert. Entscheidend ist das Datum der Stunde,
nicht der aktuelle Tag oder die gewaehlte Ansicht. Sonderstunden ohne Kurskennung
bleiben weiterhin sichtbar. Diese Erweiterung ist ab v0.4.0b2 enthalten.

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
