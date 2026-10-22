"""
SAMMY'S Radar (versão online)
Roda no GitHub Actions a cada ~10 min: busca os feeds RSS de sites confiaveis
(nerd/geek/otaku/gamer) e a listagem da Omelete, junta com o que ja existia e
grava docs/news.json, que o painel (GitHub Pages) le e atualiza sozinho.
"""
import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import feedparser
import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).parent
NEWS_FILE = BASE_DIR / "docs" / "news.json"
MAX_ITEMS = 500
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SammysRadar/1.0"}

# Fontes confiaveis verificadas (feed RSS ativo em 2026-10-22).
FEEDS = [
    {"name": "IGN Brasil",        "url": "https://br.ign.com/feed.xml",                              "category": "Jogos",         "lang": "pt"},
    {"name": "Ei Nerd",           "url": "https://www.einerd.com/feed/",                              "category": "Geral",         "lang": "pt"},
    {"name": "JBox",              "url": "https://www.jbox.com.br/feed/",                              "category": "Animes",        "lang": "pt"},
    {"name": "Otaku Pt",          "url": "https://www.otakupt.com/feed/",                              "category": "Animes",        "lang": "pt"},
    {"name": "Legião dos Heróis", "url": "https://www.legiaodosherois.com.br/feed",                    "category": "Filmes/Séries", "lang": "pt"},
    {"name": "ComicBook.com",     "url": "https://comicbook.com/feed/",                                "category": "Filmes/Séries", "lang": "en"},
    {"name": "Kotaku",            "url": "https://kotaku.com/feed",                                    "category": "Jogos",         "lang": "en"},
    {"name": "Eurogamer",         "url": "https://www.eurogamer.net/feed",                              "category": "Jogos",         "lang": "en"},
    {"name": "Anime News Network","url": "https://www.animenewsnetwork.com/all/rss.xml?ann-edition=us","category": "Animes",        "lang": "en"},
]

# Omelete nao publica RSS: buscamos a listagem de noticias direto do HTML.
OMELETE_CATEGORY_MAP = {
    "games": "Jogos",
    "séries e tv": "Filmes/Séries",
    "filmes": "Filmes/Séries",
    "mangás e animes": "Animes",
}


def parse_published(entry):
    for key in ("published", "updated", "pubDate"):
        val = entry.get(key)
        if val:
            try:
                return parsedate_to_datetime(val).astimezone(timezone.utc)
            except Exception:
                pass
    if entry.get("published_parsed"):
        return datetime(*entry["published_parsed"][:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def fetch_feed(feed):
    found = []
    try:
        parsed = feedparser.parse(feed["url"], agent=HEADERS["User-Agent"])
    except Exception as exc:
        print(f"[erro] falha ao buscar {feed['name']}: {exc}")
        return found
    for entry in parsed.entries[:20]:
        link = entry.get("link") or entry.get("id")
        if not link:
            continue
        found.append({
            "id": link,
            "title": (entry.get("title") or "Sem título").strip(),
            "link": link,
            "source": feed["name"],
            "category": feed["category"],
            "lang": feed["lang"],
            "summary": (entry.get("summary") or "")[:280],
            "published": parse_published(entry).isoformat(),
        })
    return found


def fetch_omelete():
    found = []
    try:
        resp = requests.get("https://www.omelete.com.br/noticias", headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        print(f"[erro] falha ao buscar Omelete: {exc}")
        return found
    soup = BeautifulSoup(resp.text, "html.parser")
    for article in soup.select("article.card"):
        a = article.find("a", href=True)
        title_el = article.select_one(".card__title")
        title = title_el.get_text(strip=True) if title_el else None
        if not a or not title:
            continue
        link = a["href"]
        if link.startswith("/"):
            link = "https://www.omelete.com.br" + link
        label = (a.get("data-label") or "").strip().lower()
        pub_el = article.select_one(".card__published-time")
        pub_raw = pub_el.get("data-published") if pub_el else None
        try:
            published = datetime.fromisoformat(pub_raw).astimezone(timezone.utc) if pub_raw else datetime.now(timezone.utc)
        except Exception:
            published = datetime.now(timezone.utc)
        found.append({
            "id": link,
            "title": title,
            "link": link,
            "source": "Omelete",
            "category": OMELETE_CATEGORY_MAP.get(label, "Geral"),
            "lang": "pt",
            "summary": "",
            "published": published.isoformat(),
        })
    return found


def main():
    old = json.loads(NEWS_FILE.read_text(encoding="utf-8")) if NEWS_FILE.exists() else {"items": []}
    known = {i["id"]: i for i in old.get("items", [])}

    candidates = []
    for feed in FEEDS:
        candidates.extend(fetch_feed(feed))
    candidates.extend(fetch_omelete())

    now = datetime.now(timezone.utc).isoformat()
    novos = 0
    for item in candidates:
        if item["id"] not in known:
            item["found"] = now  # quando o radar viu pela primeira vez (o painel usa pra apitar)
            known[item["id"]] = item
            novos += 1

    items = sorted(known.values(), key=lambda x: x["published"], reverse=True)[:MAX_ITEMS]
    sources = FEEDS + [{"name": "Omelete", "url": "https://www.omelete.com.br/noticias", "category": "Filmes/Séries", "lang": "pt"}]
    NEWS_FILE.write_text(json.dumps({"items": items, "last_check": now, "sources": [s["name"] for s in sources]},
                                    ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(candidates)} lidas, {novos} novas, {len(items)} no total")


if __name__ == "__main__":
    main()
