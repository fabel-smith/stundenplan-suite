## Korrigierte Schulmanager-Anleitung

- Die Installationsanleitung verweist jetzt auf **Schulmanager Online von MrIcemanLE**: https://github.com/MrIcemanLE/Schulmanager-homeassistant.
- Der Einrichtungsdialog erwartet die Integrations-Domain `schulmanager`. Das separate Projekt von rwunsch verwendet `schulmanager_online`; seine Entitäten werden in diesem Dialog derzeit nicht angeboten. Eine vollständige Anbindung dieses anderen Projekts ist nicht bestätigt.
- Ergänzt wurde eine Erklärung für leere Auswahllisten und die benötigten Kalender-/Sensor-Entitäten desselben Kindes.

Danke an @8R3N38 für den Hinweis in #2.

## Umfang und Prüfung

Dieses Wartungsrelease korrigiert die Dokumentation. **Keine Änderung an Datenabruf, Anmeldung, Abfrageintervallen oder bestehenden Einstellungen.** Bereits funktionierende Installationen müssen nicht neu eingerichtet werden.

72 automatisierte Tests bestanden, einschließlich einer neuen Prüfung, die die dokumentierte Integration mit den Auswahlfiltern abgleicht. Die Zuordnung wurde zusätzlich anhand des öffentlichen Quellcodes der beiden Schulmanager-Projekte geprüft; eine neue Live-Prüfung in Home Assistant wurde nicht durchgeführt.

Begleitend behebt **Stundenplan Card v3.8.2** die A/B-Wochenanzeige beim Blättern und erweitert die Erkennung von Raumbezeichnungen. Die Suite muss für diese Kartenkorrekturen nicht aktualisiert werden.
