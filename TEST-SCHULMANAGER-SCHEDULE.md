# Schulmanager: technische Testdetails zur Vorabversion

Fuer den gemeinsamen Praxistest: [Kurze Testanleitung](PRERELEASE_TEST.md).

Voraussetzung: Schulmanager Online mit der Aktion `schulmanager.get_schedule`
(getesteter Vertrag: v0.13.0b4, schema_version 1). Die Testkombination ist
Suite v0.4.0b1 mit Card v3.11.0-beta.1; kein regulaeres Release.

## Bestehende Einrichtung umstellen

1. Einstellungen > Geraete & Dienste > Stundenplan Suite > Konfigurieren.
2. "Neue Schulmanager-Schnittstelle verwenden" einschalten.
3. Kind und Konto auswaehlen.
4. Nur die **nicht benoetigten** Kurse markieren. Leer bedeutet: alle behalten.

Bestehende Entity-IDs und die gespeicherte Wochenauswahl bleiben erhalten.
Die bisherige Kalender-/Sensor-Anbindung ist weiterhin verfuegbar. Zum
Zurueckwechseln den Schalter ausschalten; die bisherigen Quellen bleiben
in bestehenden Eintraegen gespeichert.

## Verhalten und Grenzen

- Keine neuen Schulmanager-Anfragen: gelesen wird nur der Cache der Integration.
- Aenderungsereignisse aktualisieren nur das zugeordnete Kind/Konto.
- Kursfilter arbeiten mit Kurskennungen, nicht mit Fachnamen oder Raeumen.
- Neue Kurse bleiben sichtbar. Gespeicherte Filter bleiben auch in Ferien erhalten.
- Sonderstunden ohne Kurskennung werden nicht geraten oder ausgeblendet.
- Alle parallelen Stunden bleiben ohne expliziten Filter erhalten.
- Ausfaelle, Originalwerte, Hinweise und tatsaechliche Unterrichtszeiten bleiben erhalten.
- Geladen und leer ist etwas anderes als nicht geladen. Die Suite unterscheidet
  "Kein Unterricht", "Zeitraum nicht geladen" und veraltete/nicht verfuegbare Quellen.
- Fehlerhafte Antworten oder eine fehlende neue Aktion werden nicht unbemerkt
  durch die alte Anbindung ersetzt. Der Nutzer kann bewusst zurueckwechseln.
- Die Tageszusammenfassungen bleiben unabhaengig von der angezeigten Woche.

## Lokale Tests

### Geteilte Fachwechsel-Anzeige (lokaler Teststand 2026-10-30)

Echte Fachwechsel mit `status: changed`, `changes: [subject, ...]` und
einem abweichenden `original.subject` erhalten in `rows_table` optional
`subject_changes`, nach Wochentag geordnet. Jeder Eintrag verknuepft den
aktuellen Zelltext (`current`) mit dem urspruenglichen Text (`original`).
Die passende Testkarte zeigt links "Bisher" und rechts "Jetzt".

Das ist nur eine Darstellungsergaenzung: Es entsteht keine zweite Stunde,
kein zusaetzlicher Entfall und keine Aenderung an Schulbeginn/-ende.
Reine Raum-/Lehrerwechsel bleiben kompakt. Ohne eindeutige Originaldaten
bleibt die bisherige Anzeige erhalten. Raum-/Lehrer-Sichtbarkeit gilt
fuer beide Seiten. Bestehende Karten ignorieren die Zusatzdaten.

Fuer einen HA-Praxistest sind **beide** lokalen Staende erforderlich:
die Suite mit diesen Zusatzdaten und die neue Karte. Beide wurden am
2026-10-30 zusammen mit Schulmanager Online v0.13.0b4 nach HA uebertragen.
Die isolierte Testansicht enthaelt eine als Beispieldaten gekennzeichnete
Fachwechsel-Karte. Ein echter Fachwechsel in den Schuldaten ist noch offen.
Dieser damalige lokale Test war noch unveroeffentlicht. Die aktuelle
Vorabversion und den Rueckweg beschreibt die oben verlinkte Testanleitung.

`python -m pip install -r requirements-test.txt`

`python -m pytest -q`

Vor einer regulaeren Veroeffentlichung muessen echte Parallelkurse und Sonderstunden
mit den betroffenen Nutzern geprueft werden. Ein Kursfilter kann eine von
der Schule nicht gelieferte Zuordnung (z. B. Schwimmen/Sport) nicht erfinden.
