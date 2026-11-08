# Operion-Demo · Eine Lieferreklamation in fünf Prüffällen

**Für drei Minuten:** T01 und T03 live zeigen. **Für die technische Vertiefung:** T02, T04 und T05 anschließen. Es sind fünf Prüffälle. Auftrag 66823 kommt mehrfach vor, damit das Publikum denselben Vorgang unter verschiedenen Bedingungen beurteilen kann.

## Vor dem Gespräch

- [Operion Evidence Desk](http://127.0.0.1:3100/) öffnen. In [Twenty](http://localhost:3000/) und [ERPNext](http://localhost:8080/) im selben Browser anmelden. Einmal prüfen, ob unter **Open order 66823 records** der ERPNext-Entwurf, die Firma, der Auftragskontakt und die Reklamation erreichbar sind.
- Für T01 eine neue Anfrage über **New inquiry** beginnen. Links muss die simulierte Reklamation zu **WWI order 66823** sichtbar sein. Alte Antworten zeigen den Stand der damaligen Abfrage.
- Für die Kurzfassung den Vergleichsauftrag **31349** mit der ersten Frage aus T03 in einem zweiten Operion-Tab vorbereiten. Den Tab bei der Zeile mit Rechnung **33513** stehen lassen.
- Bei den Texteingaben unten ins Feld **Message input** klicken, die englische Frage einfügen und **Send message** anklicken. Bei einer direkten Auftragssuche die Auftragsnummer nennen. Bei der Rückfrage zur gerade gelesenen E-Mail genügt der Bezug auf diese E-Mail.

| Fall | Auftrag und Beleg | Worauf ich zeige |
|---|---|---|
| T01 · Reklamation | 66823 · Rechnung 64067 | Kundenaussage zum 18. Februar, Bestätigung vom 19. Februar, offener Mengenbeleg |
| T03 · Falscher Beleg | 31349 → Rechnung 33513; Untersuchungsauftrag 66823 | Derselbe Kunde, zwei verschiedene Aufträge |
| T02 · Fehlender Beleg | 73279 | Vollständige Abfrage, keine zugeordnete Rechnung |
| T04 · Datumsvergleich | 73485 · Rechnung 70414; optional 73302 · Rechnung 70244 | Bestätigung am erwarteten Tag beziehungsweise zwei Tage zuvor |
| T05 · Quellausfall | erneut 66823 | Dieselbe Frage aus einer neuen Sitzung bei gestörter SQL-Verbindung |

## Drei Minuten für den Hauptfall

### T01 · Was können wir dem Kunden heute antworten? · 0:00–1:50

**0:00–0:35 · Die E-Mail lesen.** Im Evidence Desk **New inquiry** und dann links **Read customer email** anklicken. Der Button übergibt die Note-ID mit dieser Frage:

> Read Twenty Note f98cc388-20d7-5609-8c2c-297ca58922ac. What did the customer report in the email, who sent it and which company do they represent?

**1 tool call** aufklappen und auf `get_complaint_context` zeigen. Unter **Customer complaint in Twenty** stehen die Kundenaussage, die Firma und die CRM-Lesezeit.

> „Der Kundenservice erhält eine E-Mail. Hanuman Dubey schreibt, sein Lager habe am 18. Februar nichts erhalten. Die Absenderadresse stimmt mit der Adresse des in Twenty verknüpften Kontakts überein. Dieser Kontakt gehört zu Tailspin Toys in North Cowden. Damit kennen wir den Ansprechpartner. Ob die Ware angekommen ist, ist weiterhin offen.“

**0:35–1:15 · Im selben Gespräch die Lieferung prüfen.** Ins Feld **Message input** klicken, diese Rückfrage senden und den Werkzeugaufruf dieser zweiten Antwort öffnen:

> Now check delivery for the order in that email. Does the recorded confirmation contradict the customer’s account? Prepare a reply for review.

Auf `get_order_delivery_evidence`, Rechnung **64067** und **2016-02-19T07:25:00** zeigen. Die Auftragsnummer kommt aus der gelesenen Note. **WWI SQL Server query time (UTC)** bezeichnet den Zeitpunkt der aktuellen Abfrage.

> „Erst mit dieser Rückfrage liest der Agent die ERP-Belege. Für den 18. Februar war die Lieferung geplant. Die Rechnung trägt eine Bestätigung vom 19. Februar um 7:25 Uhr. Der Kunde beschreibt den Tag davor. Beide Aussagen können also stimmen. Wie viele Stück sein Lager angenommen hat, geht aus der Bestätigung nicht hervor.“

**1:15–1:50 · Zur Kundenantwort kommen.** Auf **66823** klicken, den Auftrag in ERPNext zeigen und zu Operion zurückwechseln. In der Karte auf **Customer reply draft · pending human review** zeigen.

> „Für diesen Auftrag sind 48 Stück als Warenausgang gebucht. Im Entwurf bitten wir Herrn Dubey um einen Empfangsbeleg mit der Menge je Position. Den Entwurf prüft der Kundenservice vor dem Versand.“

**Falls nach dem Lieferanten gefragt wird:** In derselben Karte auf Warenausgang **305669** und Wareneingang **305626** zeigen. Letzterer verweist auf die Bestellung **1904** bei **Litware, Inc.**

> „Wir finden einen früheren Wareneingang für denselben Artikel. Um genau diese 48 Stück Litware zuordnen zu können, bräuchten wir eine Chargenzuordnung oder eine Reservierung zwischen Eingang und Ausgang.“

### T03 · Eine echte Rechnung am falschen Auftrag · 1:50–3:00

**1:50–2:10 · Den Gegenbeleg zeigen.** In den vorbereiteten Vergleichs-Tab wechseln. Zum Vorbereiten dort **New inquiry** klicken und diese Frage senden:

> Investigate delivery for order 31349. Which invoice is linked to this order? Show the delivery investigation card.

Auf **33513** und den Kunden **Tailspin Toys (North Cowden, TX)** zeigen. Danach in den Tab mit der Reklamation zu **66823** zurückwechseln.

> „Die Rechnung 33513 existiert. Sie gehört sogar demselben Kunden, Kunden-ID 65. Auf dem Beleg steht aber der Bezug zu Auftrag 31349. Genau so landet im Alltag eine glaubwürdige, aber unpassende Rechnung in der Vorgangsakte.“

**2:10–3:00 · Die falsche Zuordnung ausdrücklich verlangen.** Im Gespräch zu **66823** die folgende Frage senden. In der Antwort auf die Zeile *Invoice 33513 is absent from the linked invoices for this order and cannot support this investigation* und auf die zugeordnete Rechnung **64067** zeigen.

> Investigate delivery for order 66823. Can invoice 33513 prove that all 48 units arrived? Show the delivery investigation card.

> „Der Agent darf beide Aufträge lesen. Er darf die Rechnung des einen aber nicht als Beleg für den anderen verwenden. Der Modellaufruf wählt das Recherchewerkzeug. Beim Veröffentlichen prüft der Server, ob der Beleg zum untersuchten Auftrag gehört. Damit bekommt der Kundenservice einen begründeten Antwortentwurf, ohne dem Kunden einen unbewiesenen Empfang zu bestätigen.“

## Drei weitere Fälle für die technische Vertiefung

### T02 · Was bedeutet ein leeres Suchergebnis? · etwa 35 Sekunden

**Klicken:** **New inquiry** → **Message input** → Frage senden. In der Karte die Zeile *No linked invoice returned by WWI SQL Server* zeigen.

> Investigate delivery for order 73279. Is there a linked invoice or a recorded delivery confirmation? Show the delivery investigation card.

> „Die Abfrage ist vollständig durchgelaufen. Für Auftrag 73279 hat WWI keine zugeordnete Rechnung geliefert. Über diesen Weg kann ich den Empfang also nicht bestätigen. Ob tatsächlich geliefert wurde, bleibt offen.“

### T04 · Erkennt das System auch eine termingerechte Bestätigung? · etwa 40 Sekunden

**Klicken:** **New inquiry** → folgende Frage senden. Auf **70414**, **2016-05-31T12:30:00** und *on expected date (0 calendar days)* zeigen.

> Investigate delivery for order 73485. Compare the recorded confirmation date with the expected delivery date.

> „Bei diesem Auftrag war der 31. Mai der erwartete Termin. Die Bestätigung ist für denselben Tag um 12:30 Uhr erfasst. Die Regel vergleicht Kalendertage und berechnet null Tage Abweichung. Auch hier bleibt die Aussage auf das Datum der Bestätigung beschränkt.“

**Optionaler Gegencheck:** Noch einmal **New inquiry** klicken, die zweite Frage senden und auf Rechnung **70244** sowie **2016-05-28T08:50:00** zeigen.

> Investigate delivery for order 73302. Compare the recorded confirmation date with the expected delivery date.

> „Hier sehen Sie auch die andere Richtung: Geplant war der 30. Mai. Rechnung 70244 trägt eine Bestätigung vom 28. Mai um 8:50 Uhr. Das sind zwei Kalendertage früher.“

Beide Beispiele stammen aus der autorisierten SQL-Direktabfrage. Der automatisierte 30-Aufträge-Regressionstest prüft dieselben Datumsgrenzen mit kontrollierten Testzeitpunkten.

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

Nach der Bereitschaftsmeldung den [Evidence Desk](http://127.0.0.1:3100/) neu laden. **New inquiry** → **Read customer email** klicken und die CRM-Antwort abwarten. Im selben Gespräch dieselbe Rückfrage wie in T01 senden:

> Now check delivery for the order in that email. Does the recorded confirmation contradict the customer’s account? Prepare a reply for review.

In der **zweiten Antwort** auf die bereits gelesene Kundenaussage samt CRM-Lesezeit zeigen, danach auf die Meldung zur fehlgeschlagenen Abfrage:

> Order 66823: Operion could not query WWI SQL Server for delivery evidence this time. Whether a linked invoice or delivery confirmation exists is unknown. Please retry when WWI is available.

> „Die E-Mail von Herrn Dubey können wir weiterhin zitieren. Was diesmal fehlt, ist eine Auskunft aus WWI. Bei Auftrag 73279 war die Abfrage erfolgreich und ergab keine zugeordnete Rechnung. Hier wissen wir noch nicht einmal, ob eine vorliegt. Eine ältere Rechnung aus dem Snapshot erscheint deshalb auch nicht in dieser Antwort.“

**Nach der Web-Probe zurücksetzen:** Die zwei Befehle im Projektverzeichnis ausführen, die Bereitschaftsmeldung abwarten und die Seite neu laden. **New inquiry** → **Read customer email** und die Rückfrage aus T01 zeigen wieder die Live-Karte.

```bash
scripts/demo.sh stop
scripts/demo.sh start-wwi
```
