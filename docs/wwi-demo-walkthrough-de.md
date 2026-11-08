# Operion-Demo · Eine Lieferreklamation in fünf Prüffällen

**Für drei Minuten:** T01 und T03 live zeigen. **Für die technische Vertiefung:** T02, T04 und T05 anschließen. Es sind fünf Prüffälle. Auftrag 66823 kommt mehrfach vor, damit das Publikum denselben Vorgang unter verschiedenen Bedingungen beurteilen kann.

## Vor dem Gespräch

- Im [Evidence Desk](http://127.0.0.1:3100/) auf **Complaints** klicken. Bei einem neuen Vorgang steht unter **Customer report** die Schaltfläche **Read customer email**. Eine frühere Untersuchung lässt sich mit **Resume investigation** öffnen.
- In einem zweiten Tab die [WWI-Rechnung 33513 zu Auftrag 31349](http://127.0.0.1:3100/orders/31349/evidence/invoice/33513) öffnen. Diesen Tab für den Gegencheck in Schritt 6 bereithalten.

| Fall | Auftrag und Beleg | Worauf ich zeige |
|---|---|---|
| T01 · Reklamation | 66823 · Rechnung 64067 | Kundenaussage, Bestätigung und englischer Antwortentwurf zur Freigabe |
| T03 · Falscher Beleg | 31349 → Rechnung 33513; Untersuchungsauftrag 66823 | Derselbe Kunde, zwei verschiedene Aufträge |
| T02 · Fehlender Beleg | 73279 | Vollständige Abfrage, keine zugeordnete Rechnung |
| T04 · Datumsvergleich | 73485 · Rechnung 70414; optional 73302 · Rechnung 70244 | Bestätigung am erwarteten Tag beziehungsweise zwei Tage zuvor |
| T05 · Quellausfall | erneut 66823 | Dieselbe Frage aus einer neuen Sitzung bei gestörter SQL-Verbindung |

## Drei Minuten für den Hauptfall

**Vorführzeit: 2:40 Minuten plus 20 Sekunden Reserve.** Die deutschen Zitate sind der Sprechtext.

**1 · 0:00–0:30 · Die Reklamation lesen (T01).** Unter **Customer report** auf **Read customer email** klicken. Der Button sendet die erste Frage automatisch:

> Read Twenty Note f98cc388-20d7-5609-8c2c-297ca58922ac. What did the customer report in the email, who sent it and which company do they represent?

Unter **Customer email** auf den Absender Hanuman Dubey und die Aussage des Kunden zeigen. Rechts ist noch kein Entwurf vorhanden.

> „Herr Dubey von Tailspin Toys schreibt, am 18. Februar sei in seinem Lager nichts angekommen. Er möchte wissen, ob alle 48 Stück eingegangen sind. Twenty bestätigt, wer die E-Mail geschickt hat. Zum Wareneingang haben wir bisher die Aussage des Kunden.“

**2 · 0:30–0:50 · Im selben Chat nachfragen.** Auf **Investigate order 66823** klicken. Der Klick öffnet das Inquiry. Einen passenden Modellvorschlag mit **Tab** übernehmen und bei Bedarf bearbeiten, oder die folgende Frage eingeben. Erst **Enter** startet die Abfrage:

> Now investigate delivery for order 66823. Check whether all units were received and prepare a reply for review.

> „Ich muss die Auftragsnummer nicht wiederholen. Der Agent übernimmt die 66823 aus der Reklamation und fragt jetzt die Belege in WWI ab.“

**3 · 0:50–1:20 · Die Bestätigung lesen.** Im Chat auf *These observations concern different dates and can both be true* zeigen. Dann auf die verlinkte Rechnungsnummer **64067** klicken. Im neuen Tab auf **Expected delivery date** und **Recorded delivery confirmation** zeigen. Den Rechnungstab für Schritt 6 offen lassen.

> „Geplant war der 18. Februar. Die Rechnung enthält eine Lieferbestätigung vom 19. Februar um 7:25 Uhr. Die Aussage des Kunden betrifft den 18., die Bestätigung den Tag danach. Deshalb können beide Angaben stimmen. Wann die Ware tatsächlich ankam und wie viele Stück der Kunde annahm, lässt sich daraus allein nicht ablesen.“

**4 · 1:20–1:45 · Die 48 Stück prüfen.** Zum Chat zurückwechseln und auf **305669** klicken. Im neuen Tab **Units posted out** und unter **Prior receipts** die Bestellungen **1904** und **1902** zeigen.

> „Unser Lager hat 48 Stück ausgebucht. Für denselben Artikel sehen wir zwei frühere Wareneingänge. Eine Chargenzuordnung fehlt. Wir können also weder die 48 Stück einer dieser Bestellungen zuordnen noch dem Kunden den vollständigen Empfang bestätigen. Dafür brauchen wir seinen Empfangsbeleg mit der Stückzahl.“

**5 · 1:45–2:05 · Den Antwortentwurf zeigen (Abschluss T01).** Zum Chat zurückwechseln, **Review draft** anklicken und rechts unter **Customer reply · Draft** auf den englischen Text zeigen. Den Satz *We cannot yet confirm how many units your warehouse received* hervorheben. Anschließend auf **No email sent** und **Human approval required** zeigen.

> „Der Agent bereitet eine Antwort vor: Der Warenausgang ist belegt, die beim Kunden angekommene Menge ist noch offen. Ein Mitarbeiter prüft zuerst die Belege und gibt die Antwort frei. Bis dahin wird keine E-Mail verschickt.“

Optionaler englischer Sprechtext: “The agent drafts a reply using the warehouse and invoice records. A member of the service team reviews the evidence before sending it. No email has been sent.”

**6 · 2:05–2:40 · Eine echte Rechnung am falschen Auftrag prüfen (T03).** Im vorbereiteten Vergleichstab auf **Invoice 33513** und **Sales order 31349** zeigen. Dann zurück zum Rechnungstab **64067** aus Schritt 3 wechseln. In der Adresszeile nur die letzte Zahl von `64067` auf `33513` ändern, `/orders/66823/` stehen lassen und **Enter** drücken. Erwartet: **404** für `/orders/66823/evidence/invoice/33513`.

> „Diese Rechnung existiert und gehört sogar demselben Kunden. Unter Auftrag 31349 können wir sie öffnen. Setze ich dieselbe Rechnungsnummer bei Auftrag 66823 ein, erhalte ich 404. Der Server prüft bei jedem Klick die Zuordnung zum Auftrag. So kann der Kundenservice eine echte Rechnung aus einem anderen Vorgang nicht versehentlich als Empfangsnachweis für diese Reklamation anführen.“

## Drei weitere Fälle für die technische Vertiefung

### T02 · Was bedeutet ein leeres Suchergebnis? · etwa 35 Sekunden

**Klicken:** **New inquiry** → **Message input** → Frage senden. In der Karte die Zeile *No linked invoice returned by WWI SQL Server* zeigen.

> Investigate delivery for order 73279. Is there a linked invoice or a recorded delivery confirmation? Show the delivery investigation card.

> „Die Abfrage ist vollständig durchgelaufen. Für Auftrag 73279 hat WWI keine zugeordnete Rechnung geliefert. Über diesen Weg kann ich den Empfang also nicht bestätigen. Ob tatsächlich geliefert wurde, bleibt offen.“

### T04 · Wie liegt die Bestätigung zum erwarteten Liefertermin? · etwa 40 Sekunden

**Auftrag 73485.** Im Evidence Desk **New inquiry** anklicken, die Frage in **Send a message...** einfügen und **Enter** drücken.

> Investigate delivery for order 73485. Compare the recorded confirmation date with the expected delivery date.

Direkt in der Antwort auf **2016-05-31** und *on expected date (0 calendar days)* zeigen. Auf die Rechnungsnummer **70414** klicken. In der [Rechnungskarte](http://127.0.0.1:3100/orders/73485/evidence/invoice/70414) steht unter **Recorded delivery confirmation** der Zeitstempel **2016-05-31T12:30:00**.

> „Geplant war der 31. Mai. Die Rechnung trägt die Bestätigung vom selben Tag um 12:30 Uhr. Der Abstand beträgt null Kalendertage. Wann die Ware beim Kunden eintraf, bleibt offen.“

**Optionaler Gegencheck mit Auftrag 73302.** Zum Chat zurückwechseln. **New inquiry** anklicken und dieselbe Frage mit der zweiten Auftragsnummer senden.

> Investigate delivery for order 73302. Compare the recorded confirmation date with the expected delivery date.

Auf **2016-05-30** und *before expected date (2 calendar days)* zeigen. Über **70244** lässt sich der Zeitstempel **2016-05-28T08:50:00** in der [zweiten Rechnungskarte](http://127.0.0.1:3100/orders/73302/evidence/invoice/70244) prüfen.

> „Hier war der 30. Mai vorgesehen. Auf der Rechnung steht der 28. Mai um 8:50 Uhr, also zwei Kalendertage früher. Ob auch die Ware früher ankam, können wir aus diesem Beleg allein nicht sagen.“

**Erwartetes Verhalten bei beiden Fragen.** Die erste Ansicht zeigt den erwarteten Termin, die verlinkte Rechnung, den Bestätigungszeitpunkt, die Differenz in Kalendertagen und *Actual arrival time is unknown*. Eine Kundenbeschwerde oder ein Antwortentwurf wäre hier sachfremd.

### T05 · Was passiert, wenn die Quelle ausfällt? · etwa 45 Sekunden mit vorbereiteter Probe

**Für die kurze Vorführung:** In einem Terminal im Projektverzeichnis den folgenden isolierten Test vorbereiten. Er verbindet nur seinen eigenen WWI-Leser mit einem geschlossenen Port. Die laufende Web-Demo bleibt erreichbar.

```bash
OPERION_TEST_WWI_SQLSERVER=1 PYTHONPATH=src:tests .venv/bin/python -m unittest -v \
  test_wwi_delivery_reader.SqlServerAcceptanceTests.test_T05_unreachable_sql_with_intact_snapshot
```

**Für die Web-Vorführung:** Diesen Fall zuletzt zeigen. Im Projektverzeichnis die lokalen Operion-Demoprozesse stoppen. Sobald sie beendet sind, den Direktmodus mit geschlossenem SQL-Port starten. SQL Server, Twenty und ERPNext laufen dabei weiter.

```bash
scripts/demo.sh stop
OPERION_WWI_HOST=127.0.0.1 OPERION_WWI_PORT=1 scripts/demo.sh start-wwi
```

Nach der Bereitschaftsmeldung den [Evidence Desk](http://127.0.0.1:3100/) neu laden. **Complaints** öffnen. Bei einem bestehenden Entwurf **Resume investigation** klicken und im selben Inquiry die Rückfrage senden. Bei einem neuen Fall **Read customer email** und dann **Investigate order 66823** klicken:

> Now investigate delivery for this order and check whether all 48 units were received.

In der **zweiten Antwort** auf die bereits gelesene Kundenaussage samt CRM-Lesezeit zeigen, danach auf die Meldung zur fehlgeschlagenen Abfrage:

> Order 66823: Operion could not query WWI SQL Server for delivery evidence this time. Whether a linked invoice or delivery confirmation exists is unknown. Please retry when WWI is available.

> „Die E-Mail von Herrn Dubey können wir weiterhin zitieren. Was diesmal fehlt, ist eine Auskunft aus WWI. Bei Auftrag 73279 war die Abfrage erfolgreich und ergab keine zugeordnete Rechnung. Hier wissen wir noch nicht einmal, ob eine vorliegt. Eine ältere Rechnung aus dem Snapshot erscheint deshalb auch nicht in dieser Antwort.“

**Nach der Web-Probe zurücksetzen:** Die zwei Befehle im Projektverzeichnis ausführen, die Bereitschaftsmeldung abwarten und die Seite neu laden. Unter **Complaints** erneut **Retry investigation** klicken und die Rückfrage im Inquiry absenden. Nach erfolgreicher Prüfung erscheint der Entwurf wieder.

```bash
scripts/demo.sh stop
scripts/demo.sh start-wwi
```
