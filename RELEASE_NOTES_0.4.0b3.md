# Suite v0.4.0b3 - Vorabversion

**Nur zum freiwilligen Testen, kein regulaeres Release. Bitte vorher ein HA-Backup erstellen.**

## Passende Daten zur angezeigten Woche

Zusammen mit **Card v3.11.0-beta.2** kann die Karte datumsgenau auf die bereits
geladenen Suite-Daten zugreifen. Damit passen Datum und Unterricht auch beim
Wochenendwechsel und in der Rolling-Ansicht zusammen.

Der automatische Ansichtswechsel veraendert nicht den gemeinsamen Wochenregler
und fragt keine Schulserver ab. Kurs- und Wochentagsfilter bleiben wirksam.
Fehlende oder veraltete Unterrichtsdaten werden nicht unter einem neuen Datum
weiterverwendet. Die manuelle Wochenwahl bleibt bei -1 bis +1.

## Kurz testen

1. Suite **v0.4.0b3** und [Card **v3.11.0-beta.2**](https://github.com/fabel-smith/stundenplan-card/releases/tag/v3.11.0-beta.2)
   als Vorabversionen installieren, HA neu starten und das Dashboard neu laden.
   Die neue Schulmanager-Schnittstelle mit **Schulmanager Online v0.13.0b4** verwenden.
2. Karteneditor: **Ansicht & Rolling > Ganze Woche > Automatisch zur naechsten Woche**.
   **Ab Samstag** oder **Ab Sonntag** waehlen, Wochenwahl auf **0** stellen.
3. Pruefen, ob Datum und Unterricht gemeinsam wechseln und die Kursfilter erhalten bleiben.

Mehrere Datenwochen sind mit der neuen Schulmanager-Schnittstelle verfuegbar,
soweit sie bereits geladen wurden. Alte Quellen liefern nur ihre geladene Woche.
Bestehende Quellen und Einstellungen werden nicht automatisch umgestellt.

[Testanleitung und Rueckweg](https://github.com/fabel-smith/stundenplan-suite/blob/v0.4.0b3/PRERELEASE_TEST.md)
