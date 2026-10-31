# Gemeinsamer Vorabtest: Suite und Karte

**Vorabversionen nur fuer freiwillige Tests, kein regulaeres Update.**
Bitte vorher ein HA-Backup erstellen. Die stabile Nutzung muss nicht umgestellt werden.

## Passende Versionen

- Schulmanager Online: **v0.13.0b4**
- Stundenplan Suite: **v0.4.0b3**
- Stundenplan Card: **v3.11.0-beta.2**

Die neue Kursauswahl benoetigt alle drei passenden Staende. Bestehende Quellen
werden nicht automatisch umgestellt. Manuelle Plaene, JSON und Stundenplan24
sollen weiterhin unveraendert funktionieren.

## Vorbereitung und Einrichtung

1. HA-Backup erstellen und die bisherigen Versionen sowie die Kartenkonfiguration notieren.
2. In HACS Vorabversionen fuer die drei Projekte zulassen
   und genau die oben genannten Versionen auswaehlen. Anschliessend HA neu starten.
3. Dashboard vollstaendig neu laden; bei alter Anzeige auch den Browser-/App-Cache
   aktualisieren. Normale HACS-Karte: `type: custom:stundenplan-card`.
   Alte separate Testressourcen nicht gleichzeitig fuer denselben Kartentyp laden.
4. In der Suite unter **Konfigurieren** die **Neue Schulmanager-Schnittstelle verwenden**,
   das richtige Kind und Konto auswaehlen. Zunaechst alle Kurse sichtbar lassen.
5. Fuer den Test eine separate Karte mit dem zugehoerigen **Suite-Wochensensor**
   verwenden. Direktes Schulmanager-`wochenplan_json` nutzt die neue Schnittstelle nicht.

## Bitte kurz pruefen

- **Parallelkurse:** Ohne Filter bleiben alle Kurse erhalten. Danach nur einen
  sicher nicht benoetigten Kurs in der Suite markieren: Nur dieser verschwindet.
  Bei unbekannter Gruppenzugehoerigkeit nichts auf Verdacht ausblenden.
- **Kartenfilter:** Unter **Inhalte filtern** sind Suite-Ausschluesse erkennbar.
  Ein zusaetzlicher Filter wirkt nur auf diese Karte, nicht auf andere Karten.
- **Mehrere Raeume:** Zwei Raeume desselben Kurses bleiben sichtbar, ohne daraus
  zwei Kurse zu machen. Echte Parallelkurse bleiben getrennt.
- **Fachwechsel:** Urspruengliches und neues Fach stehen als **Bisher / Jetzt**
  nebeneinander. Reine Raum-/Lehrerwechsel bleiben kompakt; Ausfall und Hinweise
  bleiben korrekt. Ohne echten Fachwechsel diesen Punkt als nicht pruefbar melden.
- **Wochenwahl und Neustart:** Beide Wochen ansehen und HA einmal neu starten.
  Filter bleiben gespeichert; die Plaene erscheinen wieder. Noch nicht geladene
  Daten duerfen nicht als sicher unterrichtsfrei erscheinen.
- **Optional:** Ferienkalender, Kalenderhinweise sowie eine bisherige manuelle,
  JSON- oder Stundenplan24-Karte gegenpruefen. Ferien blenden Unterricht nicht aus.

## Neu in b2: Kurs nur an bestimmten Wochentagen ausblenden

Seit **v0.4.0b2** verfuegbar und in b3 weiterhin enthalten.

1. Suite **Konfigurieren** oeffnen, neue Schnittstelle und Kind/Konto bestaetigen.
2. Den gewuenschten Kurs nicht unter **An allen Tagen ausblenden** markieren.
   Falls er dort bereits steht, aus dieser Liste entfernen.
3. Unter **Nur an bestimmten Wochentagen ausblenden** den Kurs hinzufuegen.
4. Im naechsten Schritt beispielsweise nur **Montag** markieren und speichern.
5. In einer geladenen Woche pruefen: Der Kurs fehlt montags, bleibt aber dienstags
   und an anderen nicht ausgewaehlten Tagen erhalten. Andere Parallelkurse bleiben.
6. Einstellungen erneut oeffnen und nach einem Neustart pruefen. Zum Aufheben
   der Regel den Kurs wieder aus der Wochentagsliste entfernen und speichern.

Bestehende Ausschluesse gelten weiterhin an allen Tagen. Keine neue Regel wird
automatisch eingerichtet. Sonderstunden ohne Kurskennung bleiben sichtbar.
In Ferien oder bei fehlenden Daten ist das sichtbare Ergebnis erst pruefbar,
sobald eine Unterrichtswoche geladen ist. Die Wochenwahl der Suite reicht
weiterhin von der vorigen bis zur naechsten Woche, nicht bis zur uebernaechsten.
Vor einem Rueckwechsel auf b1 die Wochentagsregeln entfernen; b1 wertet sie nicht aus.

## Neu in b3 und Card beta.2: Wochenwechsel am Wochenende

1. Beide oben genannten Vorabversionen installieren, HA neu starten und das
   Dashboard vollstaendig neu laden. Schulmanager Online v0.13.0b4 kann bleiben.
2. In einer Karte mit dem Suite-Wochensensor **Ansicht & Rolling > Ganze Woche**
   oeffnen. Unter **Automatisch zur naechsten Woche** **Ab Samstag** oder
   **Ab Sonntag** waehlen. Ohne Auswahl bleibt es bei **Erst am Montag**.
3. Die Wochenwahl auf **0** stellen. Eine manuell gewaehlte andere Woche hat Vorrang.
4. Am ausgewaehlten Wochenendtag muessen Datum und Unterricht gemeinsam zur
   kommenden Woche wechseln. Auch **Ab heute (rolling)** gegenpruefen.
5. Wochentags- und Kursfilter muessen weiter gelten. Fehlende Unterrichtsdaten
   bleiben leer und erhalten einen Hinweis, statt alte Daten zu uebernehmen.

Die Karte liest nur bereits vorhandene Suite-Daten; der automatische Wechsel
verstellt nicht die gemeinsame Wochenwahl und loest keine Schulserver-Abfrage aus.
Mehrere Datenwochen liefert die neue Schulmanager-Schnittstelle. Alte Quellen
koennen weiterhin nur ihre tatsaechlich geladene Woche bereitstellen.
Die manuelle Wochenwahl bleibt bei -1 bis +1. Dieser Test erweitert sie noch
nicht auf +2 und laedt keine zusaetzlichen Wochen bei Schulmanager nach.

## Rueckmeldung

Bitte die drei Versionen, Quelle, Datum/Stunde, erwartete und tatsaechliche Anzeige
nennen. Ein anonymisierter Screenshot reicht oft. Bei Fehlern passende Logmeldung
ergaenzen; keine Zugangsdaten, Tokens oder vollstaendigen Kinderdaten posten.
Fuer Parallelkurse ist eine anonymisierte Kurskennung hilfreich.

## Zurueck zur bisherigen Version

Zuerst in der Suite die neue Schnittstelle ausschalten und die bisherigen
Kalender-/Sensorquellen bestaetigen. Dann in HACS die vorher notierten stabilen
Versionen von Suite und Karte auswaehlen, HA neu starten und das Dashboard neu laden.
Vorabversionen danach wieder deaktivieren. Falls die alte Konfiguration nicht mehr
verfuegbar ist oder der Rueckweg scheitert, das vorher erstellte Backup wiederherstellen.
Das Entfernen und Neuanlegen der Integration ist fuer diesen Test nicht erforderlich.
