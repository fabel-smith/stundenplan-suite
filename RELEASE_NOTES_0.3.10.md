## Schonendere Abrufe bei Stundenplan24

- Anfragen der Suite werden innerhalb einer Home-Assistant-Instanz nacheinander mit mindestens 0,5 Sekunden Abstand ausgefuehrt, auch bei mehreren Kindern.
- Erfolgreiche identische Abrufe werden pro Client fuer 30 Sekunden zwischengespeichert. Wechselnde Zeitstempel in Vplan-URLs entfallen; der bisherige Browser-User-Agent bleibt unveraendert.
- Bei HTTP **429/503** beachtet die Suite `Retry-After` oder verwendet ansteigende Wartezeiten. Server- und Netzwerkfehler werden einmal verzoegert wiederholt, danach pausieren die Abrufe voruebergehend.
- Bei HTTP **401/403** stoppt der betroffene Client weitere Abrufe und alternative Abrufversuche. Bitte Zugangsdaten und Berechtigung pruefen und die Integration danach neu laden.
- Abrufsperren werden als fehlgeschlagene Aktualisierung gemeldet, nicht als vermeintlich leerer Stundenplan.
- Der Hinweis zum Aktualisierungsintervall erklaert das Risiko einer IP-Sperre. Es gibt kein garantiert sicheres Intervall und keine neue starre 180-Minuten-Grenze.

## Dokumentation und Lizenz

MIT-Lizenz, Hinweise zum Datenschutz und private Meldemoeglichkeit fuer Sicherheitsluecken ergaenzt. Bitte keine Zugangsdaten oder echten Kinderdaten in oeffentlichen Issues veroeffentlichen.

## Wichtig zum Update

Vorhandene Einstellungen und Datenformate bleiben erhalten. Die neuen Abrufregeln betreffen **Stundenplan24**; die Abfrageintervalle der separaten **Schulmanager-Online-Integration** werden nicht veraendert. Nach dem Update Home Assistant neu starten.

Die automatisierten Tests verwenden simulierte HTTP-Antworten. Ein Live-Test der neuen Schutzmassnahmen mit einem echten Schulzugang steht noch aus. Die Massnahmen reduzieren unnoetige Anfragen, garantieren aber keinen Schutz vor einer anbieterseitigen Sperre.
