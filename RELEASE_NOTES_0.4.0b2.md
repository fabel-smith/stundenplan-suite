# Suite v0.4.0b2 - Vorabversion

**Nur zum freiwilligen Testen, noch kein regulaeres Update. Bitte vorher ein HA-Backup erstellen.**

## Kurse nach Wochentag ausblenden

Ein Kurs kann jetzt nur an bestimmten Wochentagen ausgeblendet werden.
So bleibt beispielsweise Kunst dienstags sichtbar, obwohl derselbe Kurs
montags nicht benoetigt wird.

Unter **Konfigurieren** gibt es zwei getrennte Auswahllisten:

- **An allen Tagen ausblenden:** bisheriger Ausschluss des gesamten Kurses.
- **Nur an bestimmten Wochentagen ausblenden:** Kurs waehlen, danach die Tage festlegen.

Einen Kurs nur in einer Liste auswaehlen. Bestehende Ausschluesse bleiben
unveraendert; neue Tagesregeln werden nicht automatisch gesetzt.
Die Karte zeigt die Tagesbeschraenkung beim Suite-Filter an.
Sonderstunden ohne Kurskennung bleiben vorsichtshalber sichtbar.

## Update und Test

Testkombination: **Suite v0.4.0b2**, **Card v3.11.0-beta.1** und
**Schulmanager Online v0.13.0b4**. Wer b1 bereits eingerichtet hat,
muss nur die Suite aktualisieren und danach **Home Assistant neu starten**.
Fuer den Wochentagsfilter ist kein neues Kartenupdate erforderlich.

Bitte pruefen: Kurs nur montags ausblenden, Dienstag und andere Kurse behalten;
Einstellungen erneut oeffnen, HA neu starten und die Regel wieder entfernen.
Bei Ferien oder fehlenden Stundenplandaten den Anzeigetest spaeter nachholen.
Die Wochenvorschau wurde nicht erweitert.

[Kurze Testanleitung und Rueckweg](https://github.com/fabel-smith/stundenplan-suite/blob/v0.4.0b2/PRERELEASE_TEST.md) ·
[Schulmanager-Einrichtung](https://github.com/fabel-smith/stundenplan-suite/blob/v0.4.0b2/SCHULMANAGER_SCHEDULE.md)

Vor einem Rueckwechsel auf b1 die Wochentagsregeln entfernen; diese werden dort
noch nicht ausgewertet. Die stabile Version bleibt unveraendert.

Danke an @heilbreitenbach fuer das konkrete Beispiel und den gemeinsamen Test!
