## Weniger Abrufe beim Start

- Bereits geladene Daten werden beim Anlegen der Sensoren wiederverwendet. Auch ein unveraenderter gespeicherter Wochenversatz loest keinen weiteren Abruf mehr aus.
- Bei Stundenplan24 werden nur noch die angezeigte Woche und bei Bedarf fehlende Tage fuer die Sensoren Heute und Morgen geladen, statt vier komplette Nachbarwochen pauschal vorzuhalten.
- Wochenwechsel und die Tages-Sensoren bleiben erhalten. Abfrageintervalle und Schutzpausen werden nicht veraendert.

## Korrekte Zuordnung von Aenderungshinweisen

Bei Schulmanager konnten Hinweise eines Parallelkurses bisher beim falschen Fach erscheinen. Zusaetzliche Aenderungsdetails werden jetzt nur bei eindeutiger Zuordnung uebernommen. Bei unklaren Daten wird nicht geraten.

Danke an @heilbreitenbach fuer die Beispiele in [Issue #3](https://github.com/fabel-smith/stundenplan-suite/issues/3).

**Die Auswahl des richtigen Parallelkurses ist damit noch nicht geloest.** Auch die Untersuchung zum fehlenden Wochenplan in [Issue #4](https://github.com/fabel-smith/stundenplan-suite/issues/4) bleibt offen.

## Zum Update

Vorhandene Einstellungen bleiben erhalten. **Nach dem Update der Suite ueber HACS Home Assistant neu starten. Ein Update der Stundenplan Card ist nicht erforderlich.**

Suite, Wochenplaene, Tages-Sensoren und Karte wurden nach einem HA-Neustart geprueft. Die vorher beobachteten langen Suite-Startwarnungen traten dabei nicht mehr auf. Die tatsaechliche Ladezeit haengt weiterhin von der Datenquelle ab.
