# LinkedIn Post Scheduler

Ein kleines Python-Werkzeug, das geplante LinkedIn-Beiträge zur richtigen Zeit
über die offizielle LinkedIn-API veröffentlicht.

## Funktionsweise

Das Scheduling ist bewusst in zwei Teile getrennt:

1. **Die Warteschlange** – `posts.json` enthält Text, Zeitpunkt und Status
   jedes Beitrags.
2. **Der Auslöser** – ein Cron-Job ruft regelmäßig `scheduler.py run` auf. Das
   Skript prüft, was fällig ist, veröffentlicht es und schreibt den Status
   zurück.

Vorteil dieser Bauweise: kein dauerhaft laufender Prozess, der abstürzen oder
beim Neustart Termine verlieren kann. Fällt ein Lauf aus, holt der nächste ihn
nach – bis zu dem über `--max-age-hours` gesetzten Zeitfenster (Standard: 48
Stunden), damit nach einem längeren Ausfall keine veralteten Beiträge
herausgehen.

## Dateien

| Datei | Zweck |
|---|---|
| `scheduler.py` | Kommandozeilenwerkzeug: einplanen, anzeigen, veröffentlichen |
| `linkedin_client.py` | Aufrufe an die LinkedIn-API |
| `posts.json` | Die Warteschlange |
| `.github/workflows/schedule.yml` | Cron-Job über GitHub Actions |

## Einrichtung

### 1. LinkedIn Developer App

1. Unter <https://www.linkedin.com/developers/apps> eine App anlegen und mit
   einer LinkedIn-Seite verknüpfen.
2. Unter *Products* das Produkt **Share on LinkedIn** (und für die
   URN-Abfrage **Sign In with LinkedIn using OpenID Connect**) hinzufügen.
3. Ein Access-Token mit dem Scope `w_member_social` erzeugen – für den ersten
   Test genügt der Token-Generator im Developer-Portal.

Mitglieder-Token sind zeitlich begrenzt (typischerweise 60 Tage). Für den
Dauerbetrieb den Refresh-Token-Ablauf einplanen oder das Token rechtzeitig
erneuern.

> Nur die offizielle API verwenden. Automatisiertes Einloggen oder Scraping
> verstößt gegen die Nutzungsbedingungen und führt zu Sperren.

### 2. Lokal einrichten

```bash
pip install -r requirements.txt
cp .env.example .env      # Token eintragen
python scheduler.py whoami   # prüft Token und zeigt die eigene URN
```

Die URN aus `whoami` kann als `LINKEDIN_AUTHOR_URN` hinterlegt werden; das
spart bei jedem Lauf einen API-Aufruf.

### 3. Beiträge einplanen

```bash
python scheduler.py add --text "Mein erster geplanter Beitrag" --at "2026-09-01 09:00"
python scheduler.py list
python scheduler.py run --dry-run    # zeigt nur an, was veröffentlicht würde
```

Zeitangaben ohne Zeitzone werden als `Europe/Berlin` gelesen (änderbar über
`SCHEDULER_TZ`). Alternativ lässt sich `posts.json` direkt bearbeiten.

## Betrieb

### Variante A: GitHub Actions (kein eigener Server nötig)

1. In den Repository-Einstellungen unter *Secrets and variables → Actions*
   anlegen:
   - `LINKEDIN_ACCESS_TOKEN`
   - `LINKEDIN_AUTHOR_URN` (optional)
2. Unter *Settings → Actions → General* bei *Workflow permissions*
   **Read and write permissions** aktivieren, damit der Status in `posts.json`
   zurückgeschrieben werden kann.

Zu beachten:

- Geplante Workflows laufen **nur auf dem Standard-Branch**. Der Workflow muss
  also nach `main` gemerged sein, sonst feuert der Cron nicht.
- GitHub verzögert geplante Läufe bei hoher Last gelegentlich um einige
  Minuten. Für Beitragszeiten ist das unkritisch.
- Über *Actions → Run workflow* lässt sich der Lauf manuell starten, im
  Standard als Dry-Run.

### Variante B: Eigener Server

```cron
*/15 * * * * cd /pfad/zum/repo && /usr/bin/python3 scheduler.py run >> scheduler.log 2>&1
```

Token in einer `.env` neben dem Skript ablegen (Rechte auf `600` setzen).

### Variante C: Nur lokal

Derselbe Cron-Eintrag bzw. die Aufgabenplanung unter Windows – funktioniert
allerdings nur, solange der Rechner zur geplanten Zeit läuft.

## Status in der Warteschlange

| Status | Bedeutung |
|---|---|
| `pending` | wartet auf Veröffentlichung |
| `posted` | veröffentlicht, mit `posted_at` und `post_urn` |
| `failed` | nach drei Fehlversuchen aufgegeben, Grund in `last_error` |
| `skipped` | zu lange überfällig, bewusst nicht nachgeholt |

## Mögliche Erweiterungen

- Bilder und Links: erfordert den zusätzlichen Upload-Ablauf
  (`/rest/images?action=initializeUpload`) vor dem Beitrag.
- Beiträge im Namen einer Unternehmensseite: `LINKEDIN_AUTHOR_URN` auf
  `urn:li:organization:<id>` setzen (benötigt den Scope `w_organization_social`).
- Statt `posts.json` eine SQLite-Datenbank, falls die Warteschlange wächst.
