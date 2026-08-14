#!/usr/bin/env python3
"""Scheduler für LinkedIn-Beiträge.

Idee: Die Beiträge liegen als Warteschlange in einer JSON-Datei. Ein Cron-Job
(GitHub Actions, Server oder lokal) ruft regelmäßig ``scheduler.py run`` auf.
Das Skript veröffentlicht alles, was fällig ist, und schreibt den Status
zurück in die Datei. Kein Dauerprozess, übersteht jeden Neustart.

Beispiele:

    python scheduler.py add --text "Hallo LinkedIn" --at "2026-09-01 09:00"
    python scheduler.py list
    python scheduler.py run --dry-run
    python scheduler.py run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from linkedin_client import DEFAULT_API_VERSION, LinkedInClient, LinkedInError

DEFAULT_QUEUE = Path(__file__).with_name("posts.json")
DEFAULT_TZ = "Europe/Berlin"

# Nach so vielen vergeblichen Versuchen gilt ein Beitrag als endgültig gescheitert.
MAX_ATTEMPTS = 3

STATUS_PENDING = "pending"
STATUS_POSTED = "posted"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"


# --------------------------------------------------------------------------
# Konfiguration & Zeit
# --------------------------------------------------------------------------


def load_dotenv(path: Path = Path(".env")) -> None:
    """Liest eine .env-Datei ein, falls vorhanden (ohne Zusatzabhängigkeit)."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def local_tz() -> ZoneInfo:
    name = os.environ.get("SCHEDULER_TZ", DEFAULT_TZ)
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        print(f"[warn] Zeitzone {name!r} unbekannt, nutze {DEFAULT_TZ}.", file=sys.stderr)
        return ZoneInfo(DEFAULT_TZ)


def parse_time(value: str) -> datetime:
    """Parst einen Zeitpunkt; ohne Zeitzone gilt die konfigurierte lokale Zone."""
    text = value.strip().replace("Z", "+00:00")
    for candidate in (text, text.replace(" ", "T")):
        try:
            parsed = datetime.fromisoformat(candidate)
            break
        except ValueError:
            continue
    else:
        raise ValueError(
            f"Zeitpunkt {value!r} nicht lesbar. Erwartet z. B. '2026-09-01 09:00' "
            "oder '2026-09-01T09:00:00+02:00'."
        )

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_tz())
    return parsed


def fmt(moment: datetime) -> str:
    return moment.astimezone(local_tz()).strftime("%Y-%m-%d %H:%M %Z")


# --------------------------------------------------------------------------
# Warteschlange
# --------------------------------------------------------------------------


def load_queue(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    posts = data.get("posts", []) if isinstance(data, dict) else data
    if not isinstance(posts, list):
        raise ValueError(f"{path} enthält keine Liste von Beiträgen.")
    return posts


def save_queue(path: Path, posts: list[dict]) -> None:
    """Schreibt atomar, damit ein Abbruch die Warteschlange nicht zerstört."""
    payload = json.dumps({"posts": posts}, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=path.name, suffix=".tmp", delete=False
    ) as handle:
        handle.write(payload)
        tmp = Path(handle.name)
    tmp.replace(path)


def due_posts(posts: list[dict], now: datetime, max_age: timedelta | None) -> list[dict]:
    due = []
    for post in posts:
        if post.get("status", STATUS_PENDING) != STATUS_PENDING:
            continue
        scheduled = parse_time(post["scheduled_time"])
        if scheduled > now:
            continue
        if max_age is not None and now - scheduled > max_age:
            post["status"] = STATUS_SKIPPED
            post["last_error"] = (
                f"Geplant für {fmt(scheduled)} und damit älter als das erlaubte "
                "Zeitfenster – nicht nachträglich veröffentlicht."
            )
            print(f"[skip] {post.get('id')} – zu alt (geplant {fmt(scheduled)})")
            continue
        due.append(post)
    return sorted(due, key=lambda p: parse_time(p["scheduled_time"]))


# --------------------------------------------------------------------------
# Befehle
# --------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    queue_path = Path(args.queue)
    posts = load_queue(queue_path)
    if not posts:
        print(f"Keine Beiträge in {queue_path}.")
        return 0

    dry_run = args.dry_run or os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

    # Konfiguration zuerst prüfen: ein Abbruch danach würde bereits gesetzte
    # Statusänderungen verwerfen.
    client = None
    if not dry_run:
        try:
            client = LinkedInClient(
                access_token=os.environ.get("LINKEDIN_ACCESS_TOKEN", ""),
                author_urn=os.environ.get("LINKEDIN_AUTHOR_URN") or None,
                api_version=os.environ.get("LINKEDIN_API_VERSION", DEFAULT_API_VERSION),
            )
        except LinkedInError as error:
            print(f"[fehler] {error}", file=sys.stderr)
            return 1

    now = datetime.now(timezone.utc)
    max_age = timedelta(hours=args.max_age_hours) if args.max_age_hours > 0 else None
    pending = due_posts(posts, now, max_age)

    if not pending:
        print(f"Nichts fällig ({fmt(now)}).")
        save_queue(queue_path, posts)  # evtl. übersprungene Beiträge festhalten
        return 0

    failures = 0
    for post in pending:
        label = post.get("id", "?")
        preview = " ".join(post["text"].split())[:70]

        if dry_run:
            print(f"[dry-run] würde posten: {label} – \"{preview}…\"")
            continue

        try:
            urn = client.create_text_post(post["text"], post.get("visibility", "PUBLIC"))
        except (LinkedInError, OSError) as error:
            failures += 1
            post["attempts"] = post.get("attempts", 0) + 1
            post["last_error"] = str(error)
            if post["attempts"] >= MAX_ATTEMPTS:
                post["status"] = STATUS_FAILED
                print(f"[fehler] {label} endgültig gescheitert: {error}", file=sys.stderr)
            else:
                # Status bleibt pending – der nächste Lauf versucht es erneut.
                print(
                    f"[fehler] {label} Versuch {post['attempts']}/{MAX_ATTEMPTS}: {error}",
                    file=sys.stderr,
                )
        else:
            post["status"] = STATUS_POSTED
            post["posted_at"] = now.isoformat()
            post["post_urn"] = urn
            post.pop("last_error", None)
            print(f"[ok] {label} veröffentlicht ({urn or 'ohne URN'})")

    save_queue(queue_path, posts)
    return 1 if failures else 0


def cmd_add(args: argparse.Namespace) -> int:
    queue_path = Path(args.queue)
    posts = load_queue(queue_path)

    scheduled = parse_time(args.at)
    post = {
        "id": args.id or f"post-{uuid.uuid4().hex[:8]}",
        "text": args.text,
        "scheduled_time": scheduled.isoformat(),
        "visibility": args.visibility,
        "status": STATUS_PENDING,
    }
    posts.append(post)
    save_queue(queue_path, posts)
    print(f"Eingeplant: {post['id']} für {fmt(scheduled)}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    posts = load_queue(Path(args.queue))
    if not posts:
        print("Warteschlange ist leer.")
        return 0

    for post in sorted(posts, key=lambda p: parse_time(p["scheduled_time"])):
        status = post.get("status", STATUS_PENDING)
        preview = " ".join(post["text"].split())[:55]
        print(
            f"{post.get('id', '?'):<16} {fmt(parse_time(post['scheduled_time'])):<22} "
            f"{status:<9} {preview}…"
        )
    return 0


def cmd_whoami(args: argparse.Namespace) -> int:
    try:
        client = LinkedInClient(
            access_token=os.environ.get("LINKEDIN_ACCESS_TOKEN", ""),
            api_version=os.environ.get("LINKEDIN_API_VERSION", DEFAULT_API_VERSION),
        )
        print(client.whoami())
    except LinkedInError as error:
        print(f"[fehler] {error}", file=sys.stderr)
        return 1
    return 0


# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scheduler für LinkedIn-Beiträge")
    parser.add_argument(
        "--queue", default=str(DEFAULT_QUEUE), help="Pfad zur Warteschlangen-Datei"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="fällige Beiträge veröffentlichen")
    run.add_argument("--dry-run", action="store_true", help="nur anzeigen, nichts posten")
    run.add_argument(
        "--max-age-hours",
        type=int,
        default=48,
        help="Beiträge, die länger überfällig sind, überspringen (0 = kein Limit)",
    )
    run.set_defaults(func=cmd_run)

    add = sub.add_parser("add", help="Beitrag einplanen")
    add.add_argument("--text", required=True)
    add.add_argument("--at", required=True, help='z. B. "2026-09-01 09:00"')
    add.add_argument("--visibility", default="PUBLIC", choices=["PUBLIC", "CONNECTIONS"])
    add.add_argument("--id", help="eigene ID statt einer generierten")
    add.set_defaults(func=cmd_add)

    listing = sub.add_parser("list", help="Warteschlange anzeigen")
    listing.set_defaults(func=cmd_list)

    who = sub.add_parser("whoami", help="eigene Person-URN abfragen")
    who.set_defaults(func=cmd_whoami)

    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"[fehler] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
