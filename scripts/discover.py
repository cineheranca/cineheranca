"""Descoberta semanal de fontes novas (GDELT + iTunes) por país.
Grava candidatas em data/candidatos.json. Para aprovar, mude "aprovar": true (ou "ignorar").
Com AUTO_APPROVE=true, as novas candidatas válidas entram direto no feeds.json (máx. 10 por rodada)."""
import json, os, re, sys, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
import feedparser, requests

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "CineFeedBot/1.0 (descoberta de feeds)"}
AUTO = os.getenv("AUTO_APPROVE", "").lower() == "true"
MIN_RATIO, MAX_AUTO = 0.3, 10
BLOCK = {"news.google.com", "youtube.com", "facebook.com", "twitter.com", "x.com", "instagram.com",
         "msn.com", "yahoo.com", "wikipedia.org", "reddit.com", "pinterest.com", "tiktok.com"}
NOW = datetime.now(timezone.utc)

def get(url, **kw):
    return requests.get(url, headers=UA, timeout=12, **kw)

def keywords(p):
    terms = re.split(r"\s+OR\s+", p["cinema"] + " OR " + p["series"])
    return [t.strip('" ').lower() for t in terms if t.strip()]

def age_days(e):
    t = e.get("published_parsed") or e.get("updated_parsed")
    return (NOW - datetime(*t[:6], tzinfo=timezone.utc)).days if t else 999

def check_news(url, kws):
    """Retorna a fração de entradas sobre cinema/TV, ou None se o feed for inválido/parado."""
    try:
        entries = feedparser.parse(get(url).content).entries[:20]
    except Exception:
        return None
    if len(entries) < 5 or min(age_days(e) for e in entries) > 30:
        return None
    hit = sum(any(k in (e.get("title", "") + " " + e.get("summary", "")).lower() for k in kws) for e in entries)
    return hit / len(entries)

def check_podcast(url):
    try:
        feed = feedparser.parse(get(url).content)
    except Exception:
        return None
    ok = [e for e in feed.entries[:10] if any("audio" in l.get("type", "") for l in e.get("links", []))]
    return feed.feed.get("title") if ok and min(age_days(e) for e in ok) <= 45 else None

def feed_urls(domain):
    urls = []
    try:
        html = get(f"https://{domain}").text
        for tag in re.findall(r"<link[^>]+>", html, re.I):
            if re.search(r"application/(rss|atom)\+xml", tag, re.I):
                m = re.search(r'href=["\']([^"\']+)', tag)
                if m: urls.append(urljoin(f"https://{domain}", m.group(1)))
    except Exception:
        pass
    urls += [f"https://{domain}/feed", f"https://{domain}/rss"]
    return list(dict.fromkeys(urls))[:5]

def find_news(p, known_domains):
    try:
        q = f"({p['cinema']}) sourcecountry:{p['gdelt']}"
        r = get("https://api.gdeltproject.org/api/v2/doc/doc",
                params={"query": q, "mode": "artlist", "format": "json", "maxrecords": 100, "timespan": "7d"})
        arts = r.json().get("articles", [])
    except Exception as ex:
        print(f"  GDELT {p['code']} falhou: {ex}", file=sys.stderr); return []
    count = Counter(a["domain"].removeprefix("www.") for a in arts)
    domains = [d for d, n in count.most_common(25) if n >= 2 and d not in BLOCK and d not in known_domains]
    kws = keywords(p)
    def work(d):
        for u in feed_urls(d):
            ratio = check_news(u, kws)
            if ratio is not None and ratio >= MIN_RATIO:
                return {"name": d, "url": u, "lang": p["lang"], "type": "news", "category": "geral",
                        "country": p["code"], "score": round(ratio, 2)}
    with ThreadPoolExecutor(8) as ex:
        return [c for c in ex.map(work, domains) if c]

def find_podcasts(p):
    out, terms = [], [p["cinema"].split(" OR ")[0], p["series"].split(" OR ")[0]]
    for term, cat in zip(terms, ("cinema", "series")):
        try:
            r = get("https://itunes.apple.com/search", params={"term": term.strip('"'), "media": "podcast",
                    "entity": "podcast", "country": p["code"], "limit": 12}).json()
        except Exception:
            continue
        for x in r.get("results", []):
            if x.get("feedUrl"):
                out.append((x["feedUrl"], cat))
    def work(item):
        url, cat = item
        title = check_podcast(url)
        if title:
            return {"name": title, "url": url, "lang": p["lang"], "type": "podcast", "category": cat,
                    "country": p["code"], "score": 0.6}
    with ThreadPoolExecutor(8) as ex:
        return [c for c in ex.map(work, out) if c]

def main():
    doc = json.loads((ROOT / "feeds.json").read_text("utf-8"))
    cpath = ROOT / "data" / "candidatos.json"
    cands = json.loads(cpath.read_text("utf-8")) if cpath.exists() else []

    # 1) aplica as decisões tomadas por você
    keep = []
    for c in cands:
        a = c.get("aprovar")
        if a is True:
            doc["feeds"].append({k: c[k] for k in ("name", "url", "lang", "type", "category", "country")})
        elif a == "ignorar":
            doc.setdefault("ignorar", []).append(c["url"])
        else:
            keep.append(c)
    cands = keep

    # 2) procura novas
    known_urls = {f["url"] for f in doc["feeds"]} | set(doc.get("ignorar", [])) | {c["url"] for c in cands}
    known_domains = {urlparse(u).netloc.removeprefix("www.") for u in known_urls}
    new = []
    for p in doc.get("paises", []):
        print("→", p["nome"])
        found = find_news(p, known_domains) + find_podcasts(p)
        for c in found:
            if c["url"] not in known_urls:
                known_urls.add(c["url"]); new.append(c)
        time.sleep(6)  # GDELT limita ~1 requisição a cada 5 s

    # 3) auto-aprova (opcional) ou deixa para revisão
    for c in new:
        c["encontrada"] = NOW.date().isoformat()
        c["aprovar"] = False
    if AUTO:
        for c in sorted(new, key=lambda c: -c["score"])[:MAX_AUTO]:
            doc["feeds"].append({k: c[k] for k in ("name", "url", "lang", "type", "category", "country")})
            c["aprovar"] = "auto"
        new = [c for c in new if c["aprovar"] != "auto"]
    cands += new
    (ROOT / "feeds.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), "utf-8")
    cpath.write_text(json.dumps(sorted(cands, key=lambda c: (c["country"], -c["score"])), ensure_ascii=False, indent=1), "utf-8")
    print(f"{len(new)} candidatas novas; {len(cands)} aguardando revisão")

if __name__ == "__main__":
    main()
