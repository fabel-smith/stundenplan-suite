## Behoben

- Vom Schulmanager als `changedLesson` gemeldeter Unterricht wird jetzt als geaendert erkannt und in der Karte hervorgehoben. Die Stunden werden weiterhin bei Unterrichtsbeginn und -ende beruecksichtigt.
- Stundennummern wie `5`, `"5"` und `"5."` werden einheitlich zugeordnet. Dadurch gehen vorhandene Fachdetails, urspruengliche Angaben und Aenderungshinweise nicht mehr wegen eines angehaengten Punkts verloren.

Danke an @MrIcemanLE fuer die Hinweise in [stundenplan-card#16](https://github.com/fabel-smith/stundenplan-card/issues/16).

## Zum Update

Vorhandene Einstellungen bleiben erhalten. Datenabruf und Abfrageintervalle werden nicht veraendert. **Nach dem Update der Suite ueber HACS Home Assistant neu starten. Ein Update der Stundenplan Card ist nicht erforderlich.**

Der normale Betrieb mit Suite und Karte wurde nach einem Neustart in Home Assistant geprueft. Die beiden Sonderfaelle sind durch automatisierte Tests abgedeckt; passende aktuelle Echtdaten lagen fuer diese Faelle nicht vor.

Nicht enthalten sind die vorgeschlagene direkte strukturierte Datenuebergabe und eine neue Aufloesung uneindeutiger Parallelstunden.
