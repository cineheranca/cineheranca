"""Lê os feeds de feeds.json, normaliza, traduz para PT-BR e grava data/items.json."""
import hashlib, html, json, os, re, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import feedparser, requests

ROOT = Path(__file__).resolve().parent.parent
MAX_AGE_DAYS, MAX_ITEMS, MAX_PER_FEED, MAX_NEW_TRANSLATIONS = 21, 400, 25, 80
UA = {"User-Agent": "CineFeedBot/1.0 (agregador RSS)"}

TV_WORDS = re.compile(r"\b(tv|series|série|séries|season|temporada|episode|episódio|streaming|netflix|hbo|disney\+|prime video|apple tv|showrunner)\b", re.I)

def clean(t, n=None):
    t = re.sub(r"<[^>]+>", " ", t or "")
    t = re.sub(r"\s+", " ", html.unescape(t)).strip()
    return (t[:n].rsplit(" ", 1)[0] + "…") if n and len(t) > n else t

def find_image(e):
    for k in ("media_thumbnail", "media_content"):
        for m in e.get(k, []) or []:
            if m.get("url") and (m.get("medium") in (None, "image") or "image" in m.get("type", "image")):
                return m["url"]
    for l in e.get("links", []):
        if l.get("rel") == "enclosure" and "image" in l.get("type", ""):
            return l["href"]
    blob = " ".join([e.get("summary", "")] + [c.get("value", "") for c in e.get("content", [])])
    m = re.search(r'<img[^>]+src=["\']([^"\']+)', blob)
    return m.group(1) if m else None

def find_audio(e):
    for l in e.get("links", []):
        if l.get("rel") == "enclosure" and "audio" in l.get("type", ""):
            return l["href"]

def when(e):
    t = e.get("published_parsed") or e.get("updated_parsed")
    return datetime(*t[:6], tzinfo=timezone.utc) if t else datetime.now(timezone.utc)

cache_path = ROOT / "data" / "translations.json"
cache = json.loads(cache_path.read_text("utf-8")) if cache_path.exists() else {}
budget = MAX_NEW_TRANSLATIONS

def translate(text, src):
    global budget
    if not text or src.startswith("pt"):
        return None
    key = hashlib.sha1(f"{src}:{text}".encode()).hexdigest()
    if key in cache:
        return cache[key]
    if budget <= 0:
        return None
    budget -= 1
    try:
        url = os.getenv("LIBRETRANSLATE_URL")
        if url:  # LibreTranslate (próprio ou com chave)
            r = requests.post(url.rstrip("/") + "/translate", timeout=30, json={
                "q": text, "source": src, "target": "pt", "format": "text",
                "api_key": os.getenv("LIBRETRANSLATE_KEY", "")})
            out = r.json()["translatedText"]
        else:    # padrão: deep-translator
            from deep_translator import GoogleTranslator
            out = GoogleTranslator(source=src, target="pt").translate(text)
        cache[key] = out
        time.sleep(0.3)
        return out
    except Exception as ex:
        print("  tradução falhou:", ex, file=sys.stderr)
        return None

def main():
    cfg = json.loads((ROOT / "feeds.json").read_text("utf-8"))["feeds"]
    old = {i["id"]: i for i in json.loads((ROOT / "data" / "items.json").read_text("utf-8"))}
    limit = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    items = dict(old)
    for f in cfg:
        if f.get("enabled") is False:
            continue
        try:
            feed = feedparser.parse(requests.get(f["url"], headers=UA, timeout=25).content)
        except Exception as ex:
            print(f"✗ {f['name']}: {ex}", file=sys.stderr); continue
        print(f"✓ {f['name']}: {len(feed.entries)} entradas")
        for e in feed.entries[:MAX_PER_FEED]:
            link = e.get("link")
            if not link: continue
            iid = hashlib.sha1(link.encode()).hexdigest()[:16]
            dt = when(e)
            if dt < limit or iid in items: continue
            title, summary = clean(e.get("title")), clean(e.get("summary"), 320)
            cat = f.get("category", "geral")
            if cat == "geral":
                cat = "series" if TV_WORDS.search(title + " " + summary) else "cinema"
            it = {"id": iid, "title": title, "summary": summary, "link": link,
                  "image": find_image(e), "published": dt.isoformat(),
                  "source": f["name"], "lang": f["lang"], "kind": f["type"], "category": cat}
            if f["type"] == "podcast":
                it["audio"] = find_audio(e)
                if not it["audio"]: continue
            if f["type"] == "video":
                it["video_id"] = e.get("yt_videoid")
                it["image"] = it["image"] or f"https://i.ytimg.com/vi/{it['video_id']}/hqdefault.jpg"
            items[iid] = it
    out = sorted((i for i in items.values() if i["published"] >= limit.isoformat()),
                 key=lambda i: i["published"], reverse=True)[:MAX_ITEMS]
    for it in out:
        if "title_pt" not in it and not it["lang"].startswith("pt"):
            t = translate(it["title"], it["lang"])
            if t:
                it["title_pt"] = t
                it["summary_pt"] = translate(it["summary"], it["lang"]) or ""
    (ROOT / "data" / "items.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), "utf-8")
    print(f"Total: {len(out)} itens")

if __name__ == "__main__":
    main()
