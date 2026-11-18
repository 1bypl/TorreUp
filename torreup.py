#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TorreUp - local, privacy-first torrent index browser.

GPL-3.0-or-later. See LICENSE.

Design goals
------------
* Runs 100% locally using only the Python standard library.
* Aggregates public torrent indexes through a pluggable "provider" layer.
* Performs all remote requests in an anonymised way: no cookies, no referer,
  generic user-agent, no query logging, no persistent state about the user.
* If a provider is unreachable it is simply skipped and the search continues
  with the remaining sources.
"""

from __future__ import annotations

import hashlib
import html
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.utils import parsedate_to_datetime
import os
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"

# --------------------------------------------------------------------------- #
# Anonymised HTTP client                                                      #
# --------------------------------------------------------------------------- #

_USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

# Optional proxy support (e.g. Tor): HTTP_PROXY / HTTPS_PROXY / ALL_PROXY or
# TOR_PROXY env variable. No proxy is required for normal operation.
def _proxy_opener():
    proxy = (os.environ.get("TOR_PROXY") or os.environ.get("ALL_PROXY")
             or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"))
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    # Explicitly disable environment proxies unless the user opted in.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


_OPENER = _proxy_opener()


def anonymous_get(url: str, timeout: float = 6.0) -> str | None:
    """Fetch a URL without sending cookies/referer and without keeping state."""
    req = urllib.request.Request(url, headers={
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "DNT": "1",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        # Deliberately NO Referer and NO Cookie header.
    })
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            raw = resp.read(2_000_000)
            charset = resp.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace")
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Local demo index (sample data so the UI is always fully functional)         #
# --------------------------------------------------------------------------- #

CATEGORIES = {
    "movies":     ("Filmy", "🎬"),
    "tv":         ("Seriale TV", "📺"),
    "games":      ("Gry", "🎮"),
    "software":   ("Oprogramowanie", "💿"),
    "music":      ("Muzyka", "🎵"),
    "ebooks":     ("E-booki", "📚"),
    "audiobooks": ("Audiobooki", "🎧"),
    "comics":     ("Komiksy", "📖"),
    "anime":      ("Anime / Dramy", "🌸"),
    "education":  ("Edukacja", "🎓"),
    "other":      ("Inne", "📦"),
}

TITLES = {
    "movies": [
        "Oppenheimer 2023 1080p WEB-DL", "Dune Part Two 2024 4K HDR",
        "The Grand Budapest Hotel 2014", "Interstellar 2014 1080p BluRay",
        "Parasite 2019 REMUX", "Everything Everywhere All At Once 2022",
        "Blade Runner 2049 4K", "Whiplash 2014 720p", "Arrival 2016",
        "The Matrix 1999 4K HDR", "Spirited Away 2001", "Inception 2010",
        "La La Land 2016", "The Dark Knight 2008", "Mad Max Fury Road 2015",
    ],
    "tv": [
        "Breaking Bad S01-S05 Complete 1080p", "The Witcher S03 4K",
        "Stranger Things S04", "Better Call Saul Complete", "Chernobyl 2019",
        "The Last of Us S02", "Dark Season 1-3", "Peaky Blinders S06",
        "Arcane S02", "Severance S02", "Wednesday S01", "The Crown S06",
    ],
    "games": [
        "Elden Ring 2024 GOG Repack", "The Witcher 3 Wild Hunt GOTY",
        "Cyberpunk 2077 Ultimate Edition", "Hollow Knight Silksong",
        "Baldur's Gate 3", "Red Dead Redemption 2", "Stardew Valley 1.6",
        "GTA V Enhanced", "Minecraft Java 1.21", "Portal 2",
        "Mass Effect Legendary Edition", "DOOM Eternal",
    ],
    "software": [
        "Blender 4.2 LTS Portable", "LibreOffice 24.2", "GIMP 2.10.36",
        "DaVinci Resolve 19", "VS Code 1.90", "Inkscape 1.4",
        "Krita 5.2", "Audacity 3.5", "VLC 3.0.21", "QGIS 3.38",
        "Unity Hub 3.x", "AutoCAD 2025",
    ],
    "music": [
        "Pink Floyd The Dark Side of the Moon FLAC", "Daft Punk Random Access Memories",
        "Kendrick Lamar GNX 2024", "The Beatles Abbey Road 1969",
        "Lana Del Rey Ultraviolence", "Coldplay A Rush of Blood to the Head",
        "Miles Davis Kind of Blue", "Adele 30", "Arctic Monkeys AM",
        "Chopin Nocturnes Complete", "Dua Lipa Radical Optimism",
    ],
    "ebooks": [
        "Dune Frank Herbert epub", "The Hobbit Tolkien", "1984 George Orwell",
        "Clean Code Robert Martin", "The Witcher Series Sapkowski",
        "Sapiens Yuval Harari", "Atomic Habits James Clear", "The Shining Stephen King",
    ],
    "audiobooks": [
        "The Hobbit Audiobook", "Dune Audiobook", "Project Hail Mary",
        "The Witcher The Last Wish", "Atomic Habits", "Sapiens Audiobook",
    ],
    "comics": [
        "Watchmen 1986 TPB", "The Dark Knight Returns", "Maus Art Spiegelman",
        "Saga Volume 1-10", "Invincible Complete", "Persepolis",
    ],
    "anime": [
        "Attack on Titan S04 1080p", "Fullmetal Alchemist Brotherhood",
        "Cyberpunk Edgerunners", "Frieren Beyond Journey's End",
        "Demon Slayer S04", "Your Name 2016", "One Punch Man S03",
        "Violet Evergarden", "Jujutsu Kaisen S02", "Crash Landing on You",
    ],
    "education": [
        "MIT Computer Science Course Collection", "Python Full Course 2024",
        "The Art of Computer Testing", "Khan Academy Complete",
        "Data Structures and Algorithms", "Learn Blender From Zero",
        "University Physics Lectures", "UX Design Masterclass",
    ],
    "other": [
        "Ubuntu 24.04 LTS DVD", "Debian 12 Netinstall", "Linux Mint 22",
        "Public Domain Movie Collection", "NASA Image Archive Pack",
        "OpenStreetMap Poland Extract",
    ],
}

EXTS_BY_CAT = {
    "movies": ["mkv", "mp4", "avi"], "tv": ["mkv", "mp4"],
    "games": ["zip", "rar", "iso", "exe"], "software": ["exe", "zip", "iso", "dmg"],
    "music": ["flac", "mp3", "m4a"], "ebooks": ["epub", "pdf", "mobi"],
    "audiobooks": ["mp3", "m4b", "flac"], "comics": ["cbz", "cbr", "pdf"],
    "anime": ["mkv", "mp4"], "education": ["mp4", "pdf", "zip"],
    "other": ["iso", "zip", "pdf"],
}

TAGS_BY_CAT = {
    "movies": ["Film", "HD", "WEB-DL", "BluRay", "4K"],
    "tv": ["Serial", "Complete", "HDTV", "WEB"],
    "games": ["PC", "Repack", "GOG", "Steam"],
    "software": ["PC", "Portable", "Multilingual"],
    "music": ["FLAC", "Lossless", "Album"],
    "ebooks": ["EPUB", "Książka", "Polski"],
    "audiobooks": ["Audio", "MP3", " Polski".strip()],
    "comics": ["Komiks", "TPB", "Skana"],
    "anime": ["Anime", "Sub", "RAW", "1080p"],
    "education": ["Kurs", "Tutorial", "PDF"],
    "other": ["ISO", "Darmowe", "OpenSource"],
}

SOURCES = ["1337x", "TPB", "Nyaa", "TorrentGalaxy", "LimeTorrents",
           "TorrentFunk", "Rutracker", "Archive.org", "LinuxTracker", "FossTorrents"]

DESCRIPTIONS = [
    "Wysokiej jakości rip z pełną obsługą języka polskiego i angielskiego. Pliki zweryfikowane, brak reklam i dodatków.",
    "Kompletna wersja z wszystkimi dodatkami i aktualizacjami. Seedowane przez społeczność przez cały rok.",
    "Oryginalna jakość, szybkie pobieranie. Dodano polskie napisy oraz plik z informacjami.",
    "Najnowsze wydanie, sprawdzone pod kątem integralności. W środku znajdziesz pełną listę plików.",
    "Zarchiwizowana kopia dostępna dzięki otwartej społeczności. Wszystkie pliki dostępne bez ograniczeń.",
]


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} PB"


def build_demo_index() -> list[dict]:
    """Deterministically build a rich sample index across all categories."""
    rng = random.Random(20241118)
    items: list[dict] = []
    now = datetime.now(timezone.utc)

    for cat, titles in TITLES.items():
        for i, title in enumerate(titles):
            seed = rng.randint(0, 4200)
            peers = rng.randint(0, max(2, seed // 3))
            size = rng.randint(80, 9000) * 1024 * 1024
            if cat in ("ebooks", "comics"):
                size = rng.randint(2, 800) * 1024 * 1024
            if cat in ("music",):
                size = rng.randint(200, 2500) * 1024 * 1024
            # skew towards recent uploads so "day/week/month" charts are useful
            roll = rng.random()
            if roll < 0.35:
                days_ago = rng.randint(0, 1)
            elif roll < 0.65:
                days_ago = rng.randint(1, 7)
            elif roll < 0.85:
                days_ago = rng.randint(7, 30)
            else:
                days_ago = rng.randint(30, 400)
            added = now - timedelta(days=days_ago, hours=rng.randint(0, 23))
            ext = rng.choice(EXTS_BY_CAT[cat])
            ihash = hashlib.sha1(f"torreup|{cat}|{i}|{title}".encode()).hexdigest()
            tags = TAGS_BY_CAT[cat][:]

            files = []
            for f in range(rng.randint(1, 6)):
                fname = f"{title[:38]}." + (f"cd{f+1}." if f else "") + ext
                files.append({"name": fname, "size": _human_size(size // (f + 1))})

            activity = "high" if seed > 300 else ("medium" if seed > 15 else "none")

            items.append({
                "id": ihash[:16],
                "infohash": ihash,
                "title": title,
                "category": cat,
                "category_label": CATEGORIES[cat][0],
                "category_icon": CATEGORIES[cat][1],
                "size_bytes": size,
                "size": _human_size(size),
                "seeds": seed,
                "peers": peers,
                "added_at": added.isoformat(),
                "added_human": added.strftime("%d.%m.%Y"),
                "days_ago": days_ago,
                "source": rng.choice(SOURCES),
                "source_url": "",
                "magnet": f"magnet:?xt=urn:btih:{ihash}&dn={urllib.parse.quote(title)}&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce",
                "description": rng.choice(DESCRIPTIONS),
                "tags": tags[:rng.randint(2, 4)],
                "files": files,
                "thumbnail": None,
                "activity": activity,
                "verified": rng.random() > 0.35,
                "language": rng.choice(["PL", "EN", "PL/EN", "Multi"]),
                "provider": "local",
            })
    return items


DEMO_INDEX = build_demo_index()


# --------------------------------------------------------------------------- #
# Provider registry - public trackers + user-defined sources
# --------------------------------------------------------------------------- #

# Every tracker from the requested list is registered. Trackers without a
# dedicated adapter are still queried through a generic HTML parser that looks
# for magnet / .torrent links. Unreachable or blocked sources are skipped.
PROVIDERS = [
    {"id": "rutracker", "name": "Rutracker", "url": "https://rutracker.org/forum/index.php",
     "search_url": "https://rutracker.org/forum/tracker.php?nm={q}", "adapter": "generic",
     "note": "Szukanie wymaga konta — search zwraca HTTP 403"},
    {"id": "tbp", "name": "The Pirate Bay", "url": "https://thepiratebay.org/browse.php",
     "search_url": "https://apibay.org/q.php?q={q}", "adapter": "apibay",
     "note": "Oficjalny API apibay.org — działa, brak JS"},
    {"id": "predb", "name": "PreDB", "url": "https://predb.me/",
     "search_url": "https://predb.me/?search={q}", "adapter": "generic",
     "note": "Strona główna jawna, ale search → 403; baza nazw release'ów bez magnetów"},
    {"id": "torrentfunk", "name": "TorrentFunk", "url": "https://www.torrentfunk.com/",
     "search_url": "https://www.torrentfunk.com/all/torrents/search/{q}.html",
     "sitemap_url": "https://www.torrentfunk.com/sitemap.xml",
     "adapter": "sitemap", "note": "Mapa XML: tysiące pozycji (bez magnetu)"},
    {"id": "torlock", "name": "TorLock", "url": "https://www.torlock.com/",
     "search_url": "https://www.torlock.com/all/torrents/{q}.html",
     "sitemap_url": "https://www.torlock.com/sitemap.xml",
     "adapter": "sitemap", "note": "Mapa XML: tysiące pozycji (bez magnetu)"},
    {"id": "1337x", "name": "1337x", "url": "https://www.1337x.to/",
     "search_url": "https://www.1337x.to/search/{q}/1/", "adapter": "generic",
     "note": "HTTP 403 — ochrona Cloudflare"},
    {"id": "pdt", "name": "Public Domain Torrents", "url": "https://www.publicdomaintorrents.info/",
     "search_url": "https://www.publicdomaintorrents.info/?s={q}", "adapter": "generic",
     "note": "Brak linków .torrent w zwracanym HTML"},
    {"id": "lime", "name": "LimeTorrents", "url": "https://www.limetorrents.fun/",
     "search_url": "https://www.limetorrents.fun/search/all/{q}/",
     "rss_url": "https://www.limetorrents.fun/rss/search/{q}",
     "adapter": "rss", "note": "RSS: 50 pozycji z hashem w enclosure"},
    {"id": "torrentdownloads", "name": "TorrentDownloads", "url": "https://www.torrentdownloads.pro/",
     "search_url": "https://www.torrentdownloads.pro/search/?search={q}",
     "rss_url": "https://www.torrentdownloads.pro/rss.xml?type=search&search={q}",
     "adapter": "rss", "note": "RSS: hash, seedy, peerzy, rozmiar"},
    {"id": "torrentdownload", "name": "TorrentDownload", "url": "https://www.torrentdownload.info/",
     "search_url": "https://www.torrentdownload.info/search?q={q}", "adapter": "generic",
     "note": "Poprawiony URL wyszukiwania"},
    {"id": "nyaa", "name": "Nyaa", "url": "https://nyaa.si/",
     "search_url": "https://nyaa.si/?q={q}&f=0&c=0_0", "adapter": "nyaa", "note": "Dedicated adapter"},
    {"id": "torrentgalaxy", "name": "TorrentGalaxy", "url": "https://torrentgalaxy.info/",
     "search_url": "https://torrentgalaxy.info/get-posts/?keywords={q}", "adapter": "generic",
     "note": "Parametr keywords — wyszukiwanie działa"},
    {"id": "fitgirl", "name": "FitGirl Repacks", "url": "https://fitgirl-repacks.site/",
     "search_url": "https://fitgirl-repacks.site/?s={q}",
     "rss_url": "https://fitgirl-repacks.site/?s={q}&feed=rss2",
     "adapter": "rss", "note": "RSS WordPressa — działa"},
    {"id": "archive", "name": "Internet Archive", "url": "https://archive.org/",
     "search_url": "https://archive.org/advancedsearch.php?q={q}", "adapter": "archive",
     "note": "Oficjalne API — działa"},
    {"id": "linuxtracker", "name": "LinuxTracker", "url": "https://linuxtracker.org/",
     "search_url": "https://linuxtracker.org/index.php?page=torrents&search={q}",
     "rss_url": "https://linuxtracker.org/rss.php?search={q}",
     "adapter": "rss", "note": "RSS bez konta: hash i rozmiar"},
    {"id": "foss", "name": "FossTorrents", "url": "https://fosstorrents.com/",
     "search_url": "https://fosstorrents.com/search/?query={q}",
     "rss_url": "https://fosstorrents.com/feed/torrents.xml",
     "rss_limit": 1200,
     "keywords": "",
     "adapter": "rss", "note": "Kanał torrentów: 1086 pozycji z hashem i linkiem .torrent"},
    {"id": "distrowatch", "name": "DistroWatch", "url": "https://distrowatch.com/dwres.php?resource=bittorrent",
     "search_url": "https://distrowatch.com/dwres.php?resource=bittorrent",
     "rss_url": "https://distrowatch.com/news/torrents.xml",
     "keywords": "linux distro distribution dystrybucja system iso",
     "adapter": "rss", "note": "RSS: najnowsze dystrybucje Linuxa"},
]

# Runtime health of each provider, updated after every search. The UI uses it
# to show green (working), yellow (tried, nothing) or gray (not tried yet).
PROVIDER_STATS: dict[str, dict] = {}
_stats_lock = threading.Lock()
_provider_lock = threading.Lock()

CUSTOM_CONFIG = (Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
                 / "torreup" / "custom_providers.json")


def load_custom_providers() -> list[dict]:
    try:
        data = json.loads(CUSTOM_CONFIG.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_custom_providers(items: list[dict]) -> None:
    CUSTOM_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CUSTOM_CONFIG.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def register_provider(p: dict) -> None:
    with _provider_lock:
        if not any(x["id"] == p["id"] for x in PROVIDERS):
            PROVIDERS.append(p)


def unregister_provider(pid: str) -> None:
    with _provider_lock:
        PROVIDERS[:] = [x for x in PROVIDERS if x["id"] != pid]


for _custom in load_custom_providers():
    register_provider(_custom)


def provider_map() -> dict[str, dict]:
    with _provider_lock:
        return {p["id"]: p for p in PROVIDERS}


def provider_payload(p: dict) -> dict:
    with _stats_lock:
        stat = dict(PROVIDER_STATS.get(p["id"], {
            "attempts": 0, "success": 0, "last_count": 0, "last_error": None,
        }))
    status = "ok" if stat["last_count"] > 0 else ("tried" if stat["attempts"] else "new")
    return {
        "id": p["id"], "name": p["name"], "url": p["url"],
        "search_url": p.get("search_url", ""),
        "adapter": bool(p.get("adapter")), "note": p["note"],
        "custom": bool(p.get("custom")), "category": p.get("category", "all"),
        "stats": stat, "status": status,
        "search_url": p.get("search_url", ""),
    }


def build_custom_provider(data: dict) -> tuple[dict | None, str | None]:
    name = str(data.get("name", "")).strip()[:60]
    search_url = str(data.get("search_url", "")).strip()
    category = str(data.get("category", "all")).strip()
    if not name or not search_url:
        return None, "Nazwa i adres URL są wymagane"
    if not (search_url.startswith("https://") or search_url.startswith("http://")):
        return None, "Adres musi zaczynać się od http:// lub https://"
    if "{q}" not in search_url:
        search_url += ("&q={q}" if "?" in search_url else "?q={q}")
    pid = "custom_" + hashlib.sha1(search_url.encode()).hexdigest()[:10]
    return {
        "id": pid, "name": name,
        "url": str(data.get("url", "")).strip() or search_url.split("?")[0],
        "search_url": search_url, "adapter": "generic",
        "note": "Własne źródło użytkownika", "category": category, "custom": True,
    }, None


def invalidate_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _activity(seed: int) -> str:
    if seed > 300:
        return "high"
    if seed > 15:
        return "medium"
    return "none"


def adapter_nyaa(query: str) -> list[dict]:
    url = "https://nyaa.si/?q=" + urllib.parse.quote(query) + "&f=0&c=0_0"
    page = anonymous_get(url)
    if not page:
        return []
    out = []
    # Rows in nyaa's table: title link /download/....torrent and /view/....
    pattern = re.compile(
        r'<tr[^>]*>.*?<a[^>]+href="/view/(\d+)"[^>]*title="([^"]*)"[^>]*>.*?'
        r'href="([^"]+\.torrent)".*?</tr>', re.S)
    for tid, title, tlink in pattern.findall(page)[:100]:
        title = html.unescape(title)
        ihash = hashlib.sha1(("nyaa" + tid).encode()).hexdigest()
        out.append({
            "id": "nyaa" + tid,
            "infohash": ihash,
            "title": title,
            "category": "anime",
            "category_label": CATEGORIES["anime"][0],
            "category_icon": CATEGORIES["anime"][1],
            "size_bytes": 0, "size": "—",
            "seeds": 0, "peers": 0,
            "added_at": datetime.now(timezone.utc).isoformat(),
            "added_human": "—", "days_ago": 0,
            "source": "Nyaa", "source_url": "https://nyaa.si/view/" + tid,
            "magnet": f"magnet:?xt=urn:btih:{ihash}&dn={urllib.parse.quote(title)}",
            "description": "Wynik z publicznego indeksu Nyaa.",
            "tags": ["Anime", "Nyaa"], "files": [], "thumbnail": None,
            "activity": "medium", "verified": False, "language": "Multi",
            "provider": "nyaa",
        })
    return out


def adapter_archive(query: str) -> list[dict]:
    q = urllib.parse.quote(f'({query}) AND mediatype:(movies OR audio OR texts OR software)')
    url = ("https://archive.org/advancedsearch.php?q=" + q +
           "&fl[]=identifier,title,mediatype,date&rows=100&page=1&output=json")
    page = anonymous_get(url)
    if not page:
        return []
    try:
        data = json.loads(page)
    except Exception:
        return []
    cat_map = {"movies": "movies", "audio": "music", "texts": "ebooks", "software": "software"}
    out = []
    for d in data.get("response", {}).get("docs", []):
        ident = d.get("identifier", "")
        title = d.get("title", ident) or ident
        if isinstance(title, list):
            title = title[0]
        mt = d.get("mediatype", "other")
        cat = cat_map.get(mt, "other")
        ihash = hashlib.sha1(("archive" + ident).encode()).hexdigest()
        out.append({
            "id": "arc" + ihash[:12], "infohash": ihash,
            "title": title[:120], "category": cat,
            "category_label": CATEGORIES[cat][0], "category_icon": CATEGORIES[cat][1],
            "size_bytes": 0, "size": "—", "seeds": 0, "peers": 0,
            "added_at": datetime.now(timezone.utc).isoformat(),
            "added_human": str(d.get("date", "—"))[:10], "days_ago": 0,
            "source": "Archive.org",
            "source_url": "https://archive.org/details/" + urllib.parse.quote(ident),
            "magnet": f"magnet:?xt=urn:btih:{ihash}&dn={urllib.parse.quote(title[:100])}",
            "description": "Zasób z Internet Archive. Pełne metadane i pliki dostępne na stronie źródłowej.",
            "tags": ["PublicDomain", CATEGORIES[cat][0]], "files": [], "thumbnail":
                f"https://archive.org/services/img/{urllib.parse.quote(ident)}",
            "activity": "medium", "verified": True, "language": "Multi",
            "provider": "archive",
        })
    return out


def guess_category(title: str) -> str:
    s = title.lower()
    rules = [
        ("anime", ["anime", "manga", "drama", "subbed", "raw"]),
        ("games", ["game", "repack", "steam", "gog", "playstation", "xbox", "nintendo"]),
        ("music", ["mp3", "flac", "album", "music", "song", "m4a"]),
        ("audiobooks", ["audiobook", "m4b"]),
        ("ebooks", ["epub", "ebook", "mobi", "pdf"]),
        ("comics", ["comic", "cbz", "cbr"]),
        ("tv", ["season", "episode", "series", "hdtv", "s01", "s02", "s03"]),
        ("movies", ["1080p", "720p", "2160p", "bluray", "webrip", "web-dl", "x264", "film", "movie"]),
        ("education", ["course", "tutorial", "lecture", "kurs"]),
        ("software", ["software", "portable", "iso", "setup", "windows", "linux"]),
    ]
    for cat, keywords in rules:
        if any(k in s for k in keywords):
            return cat
    return "other"


def parse_generic_html(page: str, provider: dict) -> list[dict]:
    """Best-effort extraction of torrent entries from an arbitrary results page."""
    decoded = html.unescape(page)
    out: list[dict] = []
    seen: set[str] = set()
    matches = list(re.finditer(
        r'magnet:\?xt=urn:btih:([0-9A-Za-z]{32,40})[^\s"\'<>]*', decoded, re.I))[:120]

    for m in matches:
        ihash = m.group(1)
        if ihash in seen:
            continue
        seen.add(ihash)
        magnet = m.group(0)

        row_start = decoded.rfind("<tr", 0, m.start())
        row_end = decoded.find("</tr>", m.end())
        if row_start != -1 and row_end != -1 and (row_end - row_start) < 4000:
            row = decoded[row_start:row_end + 5]
        else:
            row = decoded[max(0, m.start() - 600):m.end() + 250]

        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                 for c in re.split(r"(?i)</t[dh]>", row)]
        cells = [c for c in cells if len(c) > 3]

        tm = re.search(r'title="([^"]{6,})"', row, re.I)
        title = html.unescape(tm.group(1)).strip() if tm else (max(cells, key=len)[:130] if cells else "")
        # The magnet's display-name is usually the cleanest title available.
        dn = re.search(r"[?&]dn=([^&]+)", magnet)
        if dn:
            clean = urllib.parse.unquote_plus(dn.group(1)).strip()
            if len(clean) > 3:
                title = clean
        if len(title) < 4:
            continue

        ints = []
        for c in cells:
            if re.fullmatch(r"[\d\.,\s]+", c):
                digits = re.sub(r"\D", "", c)
                if digits and len(digits) < 8:
                    ints.append(int(digits))
        seeds = ints[0] if ints else 0
        peers = ints[1] if len(ints) > 1 else 0

        sm = re.search(r"(\d+(?:[.,]\d+)?)\s*(TB|GB|MB|KB|GiB|MiB|KiB)", row, re.I)
        size_txt = (sm.group(1).replace(",", ".") + " " + sm.group(2).upper()) if sm else "—"

        hm = re.search(r'href="(https?://[^"]+)"', row, re.I)
        source_url = hm.group(1) if hm else provider.get("url", "")

        forced = provider.get("category", "all")
        cat = forced if forced in CATEGORIES else guess_category(title)

        out.append({
            "id": "g" + ihash[:15], "infohash": ihash, "title": title[:130],
            "category": cat, "category_label": CATEGORIES[cat][0],
            "category_icon": CATEGORIES[cat][1],
            "size_bytes": 0, "size": size_txt, "seeds": seeds, "peers": peers,
            "added_at": datetime.now(timezone.utc).isoformat(), "added_human": "—",
            "days_ago": 0, "source": provider["name"], "source_url": source_url,
            "magnet": magnet, "torrent_url": "",
            "description":
                f"Wynik z publicznego indeksu {provider['name']}. Dane pobrane anonimowo.",
            "tags": [provider["name"], CATEGORIES[cat][0]], "files": [],
            "thumbnail": None, "activity": _activity(seeds), "verified": False,
            "language": "Multi", "provider": provider["id"],
        })

    # Fallback for pages exposing only .torrent links with a hash in the URL.
    for torrent_match in re.finditer(r'href=["\']([^"\']+\.torrent[^"\']*)["\']', decoded, re.I):
        torrent_url = html.unescape(torrent_match.group(1))
        hm = re.search(r"\b([0-9a-fA-F]{40})\b", torrent_url)
        if not hm:
            continue
        ihash = hm.group(1).lower()
        if ihash in seen:
            continue
        seen.add(ihash)
        dn = re.search(r"[?&]title=([^&]+)", torrent_url)
        title = urllib.parse.unquote_plus(dn.group(1)).strip() if dn else ""
        if len(title) < 4:
            row_start = decoded.rfind("<a", 0, torrent_match.start())
            row_end = decoded.find("</a>", torrent_match.end())
            if row_start != -1 and row_end != -1:
                title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", decoded[row_start:row_end])).strip()
        if len(title) < 4:
            continue
        cat = guess_category(title)
        out.append({
            "id": "g" + ihash[:15], "infohash": ihash, "title": title[:130],
            "category": cat, "category_label": CATEGORIES[cat][0],
            "category_icon": CATEGORIES[cat][1], "size_bytes": 0, "size": "—",
            "seeds": 0, "peers": 0, "added_at": datetime.now(timezone.utc).isoformat(),
            "added_human": "—", "days_ago": 0, "source": provider["name"],
            "source_url": provider.get("url", ""),
            "magnet": f"magnet:?xt=urn:btih:{ihash}&dn={urllib.parse.quote(title[:100])}",
            "torrent_url": urllib.parse.urljoin(provider.get("url", ""), torrent_url),
            "description": f"Wynik z publicznego indeksu {provider['name']}.",
            "tags": [provider["name"], CATEGORIES[cat][0]], "files": [],
            "thumbnail": None, "activity": "none", "verified": False,
            "language": "Multi", "provider": provider["id"],
        })
    return out


def generic_adapter(provider: dict, query: str) -> list[dict]:
    tpl = provider.get("search_url") or ""
    url = tpl.replace("{q}", urllib.parse.quote(query)) if "{q}" in tpl else tpl
    page = anonymous_get(url, timeout=4.0)
    return parse_generic_html(page, provider) if page else []


def fix_mojibake(text: str) -> str:
    """Some feeds declare Latin-1 but actually send UTF-8 bytes."""
    if not text or not re.search(r"[ÅÄâÃ€]", text):
        return text
    try:
        return text.encode("cp1252").decode("utf-8")
    except Exception:
        return text


def rss_tag(block: str, name: str) -> str:
    m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", block, re.S | re.I)
    if not m:
        return ""
    value = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", m.group(1), flags=re.S)
    return html.unescape(re.sub(r"<[^>]+>", " ", value)).strip()


def rss_attr(block: str, tag: str, attr: str) -> str:
    m = re.search(rf"<{tag}[^>]*\b{attr}=[\"']([^\"']+)[\"']", block, re.I)
    return html.unescape(m.group(1)).strip() if m else ""


def _human_bytes(size: int) -> str:
    if not size or size <= 0:
        return "—"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024:
            return str(int(value)) + " B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def _days_since(pub: str) -> int:
    try:
        dt = parsedate_to_datetime(pub)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except Exception:
        return 0


def _to_int(text: str) -> int:
    digits = re.sub(r"\D", "", text or "")
    return int(digits) if digits else 0


def _rx_int(pattern: str, text: str) -> int:
    m = re.search(pattern, text, re.I)
    return int(m.group(1)) if m else 0


def adapter_rss(provider: dict, query: str) -> list[dict]:
    """Parse RSS/Atom torrent feeds - these often expose real infohashes."""
    tpl = provider.get("rss_url") or ""
    url = tpl.replace("{q}", urllib.parse.quote(query)) if "{q}" in tpl else tpl
    xml = anonymous_get(url, timeout=5.0)
    if not xml:
        return []

    out: list[dict] = []
    seen: set[str] = set()
    for block in re.findall(r"<item[^>]*>(.*?)</item>", xml, re.S | re.I)[:provider.get("rss_limit", 100)]:
        title = fix_mojibake(rss_tag(block, "title"))
        if len(title) < 3:
            continue

        link = rss_tag(block, "link")
        guid = rss_tag(block, "guid")
        desc = fix_mojibake(rss_tag(block, "description"))
        enclosure = rss_attr(block, "enclosure", "url")

        hash_source = " ".join([rss_tag(block, "info_hash"), guid, link, enclosure, desc])
        hm = re.search(r"\b([0-9a-fA-F]{40})\b", hash_source)
        ihash = hm.group(1).lower() if hm else ""

        mm = re.search(r'magnet:\?xt=urn:btih:[^\s"\'<>]+', html.unescape(block), re.I)
        if mm:
            magnet = html.unescape(mm.group(0))
        elif ihash:
            magnet = f"magnet:?xt=urn:btih:{ihash}&dn={urllib.parse.quote(title[:100])}"
        else:
            magnet = ""

        torrent_url = ""
        for candidate in (enclosure, link):
            if ".torrent" in candidate.lower():
                torrent_url = urllib.parse.urljoin(provider["url"], candidate)
                break
        if not magnet and not torrent_url:
            continue
        if ihash and ihash in seen:
            continue
        if ihash:
            seen.add(ihash)

        seeds = _to_int(rss_tag(block, "seeders")) or _rx_int(r"Seeds?\s*[:=]\s*(\d+)", desc)
        peers = _to_int(rss_tag(block, "leechers")) or _rx_int(r"(?:Leechers?|Peers?)\s*[:=]\s*(\d+)", desc)
        raw_size = rss_tag(block, "size") or rss_attr(block, "enclosure", "length")
        size_bytes = _to_int(raw_size)
        if not size_bytes:
            size_bytes = _rx_int(r"Size\s*[:=]\s*([\d\.]+)\s*(?:GB|MB)", desc)
        size_txt = _human_bytes(size_bytes)

        cat_raw = rss_tag(block, "category")
        cat = guess_category(cat_raw + " " + title)
        for key in CATEGORIES:
            if key in cat_raw.lower() or CATEGORIES[key][0].lower() in cat_raw.lower():
                cat = key
                break

        pub = rss_tag(block, "pubDate")
        days_ago = _days_since(pub)

        out.append({
            "id": "rss" + (ihash[:14] or hashlib.sha1(title.encode()).hexdigest()[:14]),
            "infohash": ihash, "title": title[:130],
            "category": cat, "category_label": CATEGORIES[cat][0],
            "category_icon": CATEGORIES[cat][1],
            "size_bytes": size_bytes, "size": size_txt,
            "seeds": seeds, "peers": peers,
            "added_at": datetime.now(timezone.utc).isoformat(),
            "added_human": pub[:16] or "—", "days_ago": days_ago,
            "source": provider["name"],
            "source_url": urllib.parse.urljoin(provider["url"], link) if link else provider["url"],
            "magnet": magnet, "torrent_url": torrent_url,
            "description": desc[:400] or f"Wynik z kanału RSS: {provider['name']}.",
            "tags": [provider["name"], cat_raw or CATEGORIES[cat][0]],
            "files": [], "thumbnail": None, "activity": _activity(seeds),
            "verified": bool(ihash), "language": "Multi", "provider": provider["id"],
            "keywords": provider.get("keywords", ""),
        })
    return out


def adapter_apibay(query: str) -> list[dict]:
    """The Pirate Bay's public JSON API (the site itself is JavaScript-only).

    A single query returns at most 100 rows, so all six top-level categories
    are queried in parallel to collect several hundred results.
    """
    categories = ["100", "200", "300", "400", "500", "600"]

    def fetch(cat: str) -> list:
        url = ("https://apibay.org/q.php?q=" + urllib.parse.quote(query)
               + "&cat=" + cat)
        page = anonymous_get(url, timeout=5.0)
        try:
            return json.loads(page) if page else []
        except Exception:
            return []

    data: list = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for part in pool.map(fetch, categories):
            data.extend(part)

    cat_map = {"100": "movies", "200": "tv", "300": "music",
               "400": "games", "500": "software", "600": "ebooks"}
    out: list[dict] = []
    seen: set[str] = set()
    for d in data[:600]:
        ihash = str(d.get("info_hash", "")).lower()
        title = str(d.get("name", "")).strip()
        if ihash in seen:
            continue
        seen.add(ihash)
        if len(ihash) != 40 or len(title) < 3 or title == "No results returned":
            continue
        cat = cat_map.get(str(d.get("category", ""))[:3], "other")
        seeds = _to_int(str(d.get("seeders", "0")))
        peers = _to_int(str(d.get("leechers", "0")))
        size = _to_int(str(d.get("size", "0")))
        days = 0
        try:
            added = datetime.fromtimestamp(int(d.get("added", "0")), tz=timezone.utc)
            days = max(0, (datetime.now(timezone.utc) - added).days)
        except Exception:
            pass
        out.append({
            "id": "tpb" + ihash[:14], "infohash": ihash, "title": title[:130],
            "category": cat, "category_label": CATEGORIES[cat][0],
            "category_icon": CATEGORIES[cat][1],
            "size_bytes": size, "size": _human_bytes(size),
            "seeds": seeds, "peers": peers,
            "added_at": datetime.now(timezone.utc).isoformat(), "added_human": "—",
            "days_ago": days, "source": "The Pirate Bay", "source_url": "",
            "magnet": f"magnet:?xt=urn:btih:{ihash}&dn={urllib.parse.quote(title[:100])}",
            "torrent_url": "", "description": "Wynik z publicznego API The Pirate Bay.",
            "tags": ["TPB", CATEGORIES[cat][0]], "files": [], "thumbnail": None,
            "activity": _activity(seeds), "verified": True, "language": "Multi",
            "provider": "tbp", "keywords": "",
        })
    return out


def adapter_sitemap(provider: dict, query: str) -> list[dict]:
    """Read torrent URLs from XML sitemaps (works even when HTML gives 403)."""
    index = anonymous_get(provider.get("sitemap_url", ""), timeout=5.0)
    if not index:
        return []
    subs = [html.unescape(s.strip()) for s in
            re.findall(r"<loc>(.*?)</loc>", index, re.S | re.I)]
    if not subs:
        return []
    target = next((s for s in subs if "map_all_1.xml" in s), subs[0])
    xml = anonymous_get(target, timeout=7.0)
    if not xml:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for loc in re.findall(r"<loc>(.*?)</loc>", xml, re.S | re.I)[:800]:
        url = html.unescape(loc.strip())
        m = re.search(r"/torrent/(\d+)/([^/]+?)\.html", url, re.I)
        if not m:
            continue
        tid, slug = m.group(1), urllib.parse.unquote(m.group(2))
        title = re.sub(r"[_-]+", " ", slug).strip()[:130]
        if len(title) < 4 or tid in seen:
            continue
        seen.add(tid)
        cat = guess_category(title)
        out.append({
            "id": "sm" + tid, "infohash": "", "title": title,
            "category": cat, "category_label": CATEGORIES[cat][0],
            "category_icon": CATEGORIES[cat][1],
            "size_bytes": 0, "size": "—", "seeds": 0, "peers": 0,
            "added_at": datetime.now(timezone.utc).isoformat(),
            "added_human": "—", "days_ago": 0,
            "source": provider["name"], "source_url": url,
            "magnet": "", "torrent_url": "",
            "description": f"Pozycja z mapy XML {provider['name']}. Otwórz źródło, aby pobrać torrent.",
            "tags": [provider["name"], CATEGORIES[cat][0]], "files": [],
            "thumbnail": None, "activity": "none", "verified": False,
            "language": "Multi", "provider": provider["id"], "keywords": "",
        })
    return out


ADAPTERS = {"nyaa": adapter_nyaa, "archive": adapter_archive,
            "rss": adapter_rss, "apibay": adapter_apibay, "sitemap": adapter_sitemap}


def run_provider(provider: dict, query: str) -> tuple[list[dict], str | None]:
    try:
        adapter = provider.get("adapter")
        if adapter == "generic":
            return generic_adapter(provider, query), None
        if adapter == "rss":
            return adapter_rss(provider, query), None
        if adapter == "sitemap":
            return adapter_sitemap(provider, query), None
        if adapter in ADAPTERS:
            return ADAPTERS[adapter](query), None
        return [], None
    except Exception as exc:
        return [], str(exc)


# --------------------------------------------------------------------------- #
# Search engine                                                               #
# --------------------------------------------------------------------------- #

_cache: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 60
_cache_lock = threading.Lock()


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _script_counts(text: str) -> tuple[int, int, int]:
    cjk = len(re.findall(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", text))
    cyr = len(re.findall(r"[\u0400-\u04ff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return cjk, cyr, latin


def matches_query(item: dict, query: str) -> bool:
    """Reject results unrelated to the phrase or in an unrelated script.

    Several public feeds ignore the search parameter and always return their
    latest items (e.g. Linux distros or Japanese manga), so every remote
    result is checked before it reaches the UI.
    """
    if not query:
        return True
    title = item.get("title", "")
    q_cjk, q_cyr, _ = _script_counts(query)
    t_cjk, t_cyr, t_latin = _script_counts(title)
    # A Latin query must not surface titles containing CJK/katakana or Cyrillic
    # runs - even if the rest of the title is Latin (e.g. "TVアニメ ... FLAC").
    if q_cjk == 0 and re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]{2,}", title):
        return False
    if q_cyr == 0 and re.search(r"[\u0400-\u04ff]{3,}", title):
        return False
    tokens = [tok for tok in re.split(r"\W+", _normalise(query)) if len(tok) >= 3]
    if not tokens:
        return True
    haystack = " ".join([
        title, " ".join(item.get("tags") or []),
        (item.get("description") or "")[:200], item.get("source", ""),
        item.get("keywords", ""),
    ]).lower()
    hits = sum(1 for tok in tokens if tok in haystack)
    required = 1 if len(tokens) == 1 else max(1, len(tokens) // 2)
    return hits >= required


def search_local(query: str = "", category: str = "all") -> list[dict]:
    q = _normalise(query)
    results = []
    for item in DEMO_INDEX:
        if category != "all" and item["category"] != category:
            continue
        if q and q not in _normalise(item["title"]) and q not in _normalise(" ".join(item["tags"])):
            continue
        results.append(dict(item))
    return results


def remote_results(query: str) -> tuple[list[dict], list[str]]:
    """Query every registered source in parallel; failures never abort the search."""
    with _provider_lock:
        targets = [p for p in PROVIDERS if p.get("adapter") in ("generic",) or p.get("adapter") in ADAPTERS]

    out: list[dict] = []
    scanned: list[str] = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(run_provider, p, query): p for p in targets}
        for future in as_completed(futures):
            provider = futures[future]
            results, error = future.result()
            with _stats_lock:
                stat = PROVIDER_STATS.setdefault(provider["id"], {
                    "attempts": 0, "success": 0, "last_count": 0, "last_error": None,
                })
                stat["attempts"] += 1
                stat["last_count"] = len(results)
                stat["last_error"] = error
                stat["last_query"] = query
                if results:
                    stat["success"] += 1
            if results:
                scanned.append(provider["name"])
                out.extend(results[:1200])
    return out[:3000], scanned


def sort_results(items: list[dict], sort: str) -> list[dict]:
    key = {
        "seeds": lambda x: x["seeds"],
        "peers": lambda x: x["peers"],
        "size": lambda x: x["size_bytes"],
        "date": lambda x: x["days_ago"] * -1,  # newer first
        "relevance": lambda x: (x["seeds"] + 1) / (x["days_ago"] + 2),
    }.get(sort, lambda x: x["seeds"])
    return sorted(items, key=key, reverse=True)


def do_search(query: str, category: str = "all", sort: str = "seeds",
              period: str = "all", allow_remote: bool = True,
              refresh: bool = False) -> dict:
    started = time.time()
    cache_key = f"{_normalise(query)}|{category}|{sort}|{period}|{allow_remote}"
    if not refresh:
        with _cache_lock:
            cached = _cache.get(cache_key)
            if cached and time.time() - cached[0] < _CACHE_TTL:
                return cached[1]

    results = search_local(query, category)

    # "Najlepsze torrenty" - restrict to a period window.
    if period in ("day", "week", "month"):
        max_days = {"day": 1, "week": 7, "month": 30}[period]
        results = [r for r in results if r["days_ago"] <= max_days]

    if query and allow_remote:
        remote, _names = remote_results(query)
        if period in ("day", "week", "month"):
            remote = [r for r in remote if r["days_ago"] <=
                      {"day": 1, "week": 7, "month": 30}[period]]
        results.extend(remote)

    if query:
        results = [r for r in results if matches_query(r, query)]

    # Status/counters reflect only results that survived the relevance filter.
    counts: dict[str, int] = {}
    active_sources: list[str] = []
    for result in results:
        pid = result.get("provider", "")
        if pid and pid != "local":
            counts[pid] = counts.get(pid, 0) + 1
            src = result.get("source", "")
            if src and src not in active_sources:
                active_sources.append(src)
    # Do not wipe the last real search status on an empty / trending query.
    if query and allow_remote:
        with _stats_lock:
            for pid, stat in PROVIDER_STATS.items():
                stat["last_count"] = counts.get(pid, 0)
    scanned = (["Lokalny indeks"] if any(r.get("provider") == "local" for r in results) else [])
    scanned.extend(active_sources)

    results = sort_results(results, sort)
    payload = {
        "query": query,
        "count": len(results),
        "results": results,
        "sources": scanned,
        "elapsed": round(time.time() - started, 3),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with _cache_lock:
        _cache[cache_key] = (time.time(), payload)
    return payload


# --------------------------------------------------------------------------- #
# HTTP server                                                                 #
# --------------------------------------------------------------------------- #

MIME = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
    ".woff2": "font/woff2", ".ttf": "font/ttf",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "TorreUp/" + VERSION

    def log_message(self, fmt, *args):
        # Privacy: never log query strings or requested paths.
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # Privacy / security headers
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, private")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data: https:; connect-src 'self'; "
                         "style-src 'self' 'unsafe-inline'; script-src 'self'; font-src 'self' data:")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _static(self, path: str):
        rel = path.lstrip("/")
        if rel in ("", "index.html"):
            target = WEB / "index.html"
        elif rel.startswith("static/"):
            target = WEB / rel[len("static/"):]
        else:
            target = WEB / rel
        target = target.resolve()
        if not str(target).startswith(str(WEB.resolve())) or not target.is_file():
            self._send(404, {"error": "Not found"})
            return
        ctype = MIME.get(target.suffix.lower(), "application/octet-stream")
        self._send(200, target.read_bytes(), ctype)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)
        one = lambda k, d="": (params.get(k) or [d])[0]

        try:
            if path.startswith("/api/"):
                if path == "/api/health":
                    return self._send(200, {"status": "ok", "version": VERSION,
                                            "providers": len(PROVIDERS)})
                if path == "/api/providers":
                    with _provider_lock:
                        sources = [provider_payload(p) for p in PROVIDERS]
                    return self._send(200, sources)
                if path == "/api/providers/custom":
                    with _provider_lock:
                        return self._send(200, [provider_payload(p) for p in PROVIDERS if p.get("custom")])
                if path == "/api/categories":
                    return self._send(200, [{"id": k, "label": v[0], "icon": v[1]}
                                            for k, v in CATEGORIES.items()])
                if path == "/api/search":
                    payload = do_search(
                        one("q"), one("category", "all"), one("sort", "seeds"),
                        one("period", "all"), one("remote", "1") != "0",
                        one("refresh") == "1")
                    return self._send(200, payload)
                if path == "/api/trending":
                    payload = do_search("", one("category", "all"), "seeds",
                                        one("period", "week"), False)
                    return self._send(200, payload)
                if path == "/api/detail":
                    q = one("q")
                    for r in DEMO_INDEX:
                        if r["id"] == q or r["infohash"] == q:
                            return self._send(200, r)
                    # try remote by title
                    remote, _ = remote_results(q)
                    if remote:
                        return self._send(200, remote[0])
                    return self._send(404, {"error": "Not found"})
                if path == "/api/image":
                    url = one("url")
                    if not url.startswith("https://"):
                        return self._send(400, {"error": "invalid url"})
                    req = urllib.request.Request(url, headers={
                        "User-Agent": random.choice(_USER_AGENTS), "DNT": "1"})
                    try:
                        with _OPENER.open(req, timeout=6) as resp:
                            data = resp.read(3_000_000)
                            ctype = resp.headers.get_content_type() or "image/jpeg"
                    except Exception:
                        return self._send(404, {"error": "image unavailable"})
                    return self._send(200, data, ctype)
                if path == "/api/torrent":
                    url = one("url")
                    if not url.startswith(("https://", "http://")):
                        return self._send(400, {"error": "invalid url"})
                    req = urllib.request.Request(url, headers={
                        "User-Agent": random.choice(_USER_AGENTS), "DNT": "1"})
                    try:
                        with _OPENER.open(req, timeout=8) as resp:
                            data = resp.read(10_000_000)
                        filename = os.path.basename(urllib.parse.urlparse(url).path) or "torrent.torrent"
                        filename = re.sub(r"[^A-Za-z0-9._-]", "_", filename)[:120]
                    except Exception:
                        return self._send(404, {"error": "torrent unavailable"})
                    return self._send(200, data, "application/x-bittorrent",
                                      {"Content-Disposition": f'attachment; filename="{filename}"'})
                if path == "/api/license":
                    try:
                        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
                    except Exception:
                        text = "GPL-3.0-or-later — see https://www.gnu.org/licenses/gpl-3.0.html"
                    return self._send(200, text, "text/plain; charset=utf-8")
                if path == "/api/config":
                    return self._send(200, {
                        "version": VERSION,
                        "languages": ["pl", "en", "fr", "de", "ru", "es", "it"],
                        "themes": ["midnight", "aurora", "ember", "mono", "forest"],
                    })
                return self._send(404, {"error": "Unknown endpoint"})
            return self._static(path)
        except Exception as exc:
            return self._send(500, {"error": str(exc)})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/providers/custom":
            length = int(self.headers.get("Content-Length", 0))
            try:
                data = json.loads(self.rfile.read(length))
            except Exception:
                data = {}
            provider, error = build_custom_provider(data)
            if error:
                return self._send(400, {"error": error})
            custom = load_custom_providers()
            if any(x["id"] == provider["id"] for x in custom):
                return self._send(409, {"error": "To źródło jest już dodane"})
            custom.append(provider)
            save_custom_providers(custom)
            register_provider(provider)
            invalidate_cache()
            return self._send(201, provider_payload(provider))
        if parsed.path == "/api/client/open":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw)
            except Exception:
                data = {}
            magnet = data.get("magnet", "")
            client = data.get("client", "system")
            if not magnet.startswith("magnet:") and not magnet.startswith("http"):
                return self._send(400, {"ok": False, "error": "Invalid link"})
            opened = False
            try:
                if sys.platform.startswith("linux"):
                    os.system(f'xdg-open "{magnet}" >/dev/null 2>&1 &')
                elif sys.platform == "darwin":
                    os.system(f'open "{magnet}" >/dev/null 2>&1 &')
                else:
                    os.system(f'start "" "{magnet}"')
                opened = True
            except Exception:
                opened = False
            return self._send(200, {"ok": opened, "client": client})
        return self._send(404, {"error": "Unknown endpoint"})

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/providers/custom":
            pid = (urllib.parse.parse_qs(parsed.query).get("id") or [""])[0]
            save_custom_providers([x for x in load_custom_providers() if x["id"] != pid])
            unregister_provider(pid)
            with _stats_lock:
                PROVIDER_STATS.pop(pid, None)
            invalidate_cache()
            return self._send(200, {"ok": True})
        return self._send(404, {"error": "Unknown endpoint"})


def main():
    port = int(os.environ.get("TORREUP_PORT", "7788"))
    host = os.environ.get("TORREUP_HOST", "127.0.0.1")
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"\n  TorreUp {VERSION} - lokalna przeglądarka torrentów")
    print(f"  Interfejs:  http://{host}:{port}")
    print(f"  Indeks:     {len(DEMO_INDEX)} pozycji (dane przykładowe)")
    print(f"  Prywatność: brak logów, brak ciasteczek, zapytania anonimowe\n")
    print("  Naciśnij Ctrl+C, aby zakończyć.\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  Zamykanie TorreUp...")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
