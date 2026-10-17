"""Auto-fill photo, descriptions and specs of new bike models using web-grounded Gemini search."""
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)

SPEC_FIELDS = ["frame", "motor", "battery", "range", "suspension", "groupset", "brakes", "wheels", "weight"]
CATEGORY_HINT = {"gravel": "gravel bike (non-electric)", "egravel": "electric gravel bike", "ebike_mtb": "electric mountain bike"}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept-Language": "it-IT,it;q=0.9,en;q=0.8"}
BAD_IMG = re.compile(r"placeholder|logo|icon|sprite|favicon|avatar|banner|default", re.I)
META_IMG = [re.compile(p, re.I) for p in (
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|og:image:secure_url|twitter:image)["\'][^>]*content=["\']([^"\']+)',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\'](?:og:image|twitter:image)["\']',
    r'"image"\s*:\s*\[?\s*"(https?://[^"]+)"',
)]

PROMPT = """Search the web for the bike model "{model}" ({hint}){year_txt}.
Use the manufacturer's official product page as the main source (retailers only to fill gaps).{year_rule}
Reply with ONLY a JSON object, no markdown:
{{"name": official model name,
 "description_it": 2 short sentences in Italian for customers renting it (what it is, where it shines),
 "description_en": same in English,
 "specs": {{"frame": "", "motor": "", "battery": "", "range": "", "suspension": "", "groupset": "", "brakes": "", "wheels": "", "weight": ""}},
 "pages": [up to 5 product page URLs you actually found, official first],
 "images": [direct product photo URLs you actually found, if any],
 "year_confirmed": true only if the sources explicitly show these specs belong to the requested model year, else false}}
Each spec is one short line; use "" when not stated in sources or not applicable (e.g. motor/battery/range for non-electric bikes).
Never invent URLs."""


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    return json.loads(m.group(0)) if m else {}


YEAR_RULE = """
IMPORTANT: the bike is model year {year} (MY{yy}). Use ONLY sources about the {year} version: specs and photos of other
model years are wrong (components and colours change every year). Prefer pages whose URL or title mentions {year}/MY{yy}.
If you cannot find information for {year}, leave the specs empty and set year_confirmed to false."""


def _year_tokens(year: Optional[str]) -> list:
    return [year, f"my{year[2:]}", f"my {year[2:]}", f"my-{year[2:]}"] if year else []


def _other_year(text: str, year: str) -> bool:
    """True if `text` mentions some model year but not `year` (e.g. a 2024 review page when we need 2026)."""
    found = set(re.findall(r"(?<!\d)(20[12]\d)(?!\d)", text))
    return bool(found) and year not in found


async def _research(model: str, category: str, year: Optional[str] = None) -> tuple[dict, list]:
    chat = (LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=f"enrich-{model}-{year}",
                    system_message="You are a precise bicycle specification researcher.")
            .with_model("gemini", "gemini-2.5-flash").with_tools([{"googleSearch": {}}]))
    r = await chat.send_message_with_tools(UserMessage(text=PROMPT.format(
        model=model, hint=CATEGORY_HINT.get(category, "bike"),
        year_txt=f", model year {year}" if year else "",
        year_rule=YEAR_RULE.format(year=year, yy=year[2:]) if year else "")))
    grounded = []
    for meta in getattr(r.raw, "vertex_ai_grounding_metadata", None) or []:
        for ch in (meta or {}).get("groundingChunks", []) or []:
            uri = (ch.get("web") or {}).get("uri")
            if uri:
                grounded.append(uri)
    return _json(r.content), grounded


async def _is_photo(c: httpx.AsyncClient, url: str) -> bool:
    if not url.startswith("https://") or BAD_IMG.search(url):
        return False
    try:
        r = await c.get(url, headers=UA)
        return r.status_code == 200 and r.headers.get("content-type", "").startswith("image/") and len(r.content) > 15000
    except Exception:
        return False


def _page_head(html: str) -> str:
    """Title + og/twitter text + JSON-LD names: where shops and brands state the model year."""
    parts = re.findall(r"<title[^>]*>(.*?)</title>", html[:200000], re.S | re.I)
    parts += re.findall(r'<meta[^>]+(?:property|name)=["\'](?:og:title|og:description|twitter:title|description)["\'][^>]*content=["\']([^"\']+)', html, re.I)
    parts += re.findall(r'"(?:name|model|modelYear|releaseDate)"\s*:\s*"([^"]{0,200})"', html[:400000])
    return " ".join(parts).lower()


async def _find_photo(images: list, pages: list, brand: str = "", exclude: Optional[str] = None,
                      year: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
    """Return (photo_url, source_page_url): first verified image from direct candidates or page meta tags.
    Pages are resolved first so the manufacturer's own site (host containing the brand) is preferred.
    With `year`, a photo is accepted only if the image URL, the page URL or the page title/metadata mention that
    model year, and never from pages that only mention a different year."""
    toks = _year_tokens(year)
    has_year = lambda t: any(k in t.lower() for k in toks)  # noqa: E731
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
        for url in images:
            if url != exclude and (not year or has_year(url)) and await _is_photo(c, url):
                return url, None
        fetched = []
        for page in dict.fromkeys(pages):
            try:
                r = await c.get(page, headers=UA)
            except Exception:
                continue
            if r.status_code == 200:
                fetched.append(r)
        fetched.sort(key=lambda r: 0 if brand and brand in (r.url.host or "") else 1)
        for r in fetched:
            page_url, head = str(r.url), _page_head(r.text) if year else ""
            if year and _other_year(page_url, year):
                continue
            page_ok = not year or has_year(page_url) or has_year(head)
            for rx in META_IMG:
                for img in rx.findall(r.text)[:3]:
                    img = img.replace("&amp;", "&")
                    if year and not (page_ok or has_year(img)):
                        continue
                    if year and _other_year(img, year) and not page_ok:
                        continue
                    if img != exclude and await _is_photo(c, img):
                        return img, str(r.url)
    return None, None


async def lookup(model: str, category: str, year: Optional[str] = None, need_photo: bool = True,
                 exclude: Optional[str] = None) -> dict:
    """Search the web for a model (of a given model year). Returns found data only (nothing is saved).
    With `year`, specs are returned only if the sources confirm that model year."""
    info, grounded = await _research(model, category, year)
    pages = [u for u in (info.get("pages") or []) if isinstance(u, str)] + grounded
    brand = model.split()[0].lower() if model.split() else ""
    photo, page = (None, None)
    if need_photo:
        photo, page = await _find_photo([u for u in (info.get("images") or []) if isinstance(u, str)], pages, brand, exclude, year)
        if not photo:  # search results vary between runs: one more attempt
            try:
                info2, grounded2 = await _research(model, category, year)
                pages += [u for u in (info2.get("pages") or []) if isinstance(u, str)] + grounded2
                photo, page = await _find_photo([u for u in (info2.get("images") or []) if isinstance(u, str)], pages, brand, exclude, year)
            except Exception as e:
                logger.warning("Lookup retry failed for %s: %s", model, e)
    clean = lambda v: v.strip() if isinstance(v, str) else ""  # noqa: E731
    confirmed = (not year) or info.get("year_confirmed") is True
    specs = {f: clean((info.get("specs") or {}).get(f)) for f in SPEC_FIELDS} if confirmed else {}
    return {
        "year": year or "",
        "year_confirmed": confirmed,
        "image_url": photo or "",
        "source_url": page or (pages[0] if pages else ""),
        "description": clean(info.get("description_it")),
        "description_en": clean(info.get("description_en")),
        "specs": {f: v for f, v in specs.items() if v},
    }


async def enrich_bike(db, bike_id: str, force: bool = False) -> dict:
    """Fill only the empty fields of a bike (photo, descriptions, specs). Never overwrites admin data."""
    bike = await db.bikes.find_one({"id": bike_id}, {"_id": 0})
    if not bike or (bike.get("enriched_at") and not force):
        return {"ok": False, "reason": "skipped"}
    await db.bikes.update_one({"id": bike_id}, {"$set": {"enriched_at": datetime.now(timezone.utc).isoformat()}})
    model = bike.get("sheet_model") or bike["name"]
    try:
        found = await lookup(model, bike["category"], bike.get("model_year"), need_photo=not bike.get("image_url"))
    except Exception as e:
        logger.warning("Enrich research failed for %s: %s", model, e)
        await db.bikes.update_one({"id": bike_id}, {"$set": {"enrich_error": str(e)[:200]}})
        return {"ok": False, "reason": "research_failed"}
    upd = {"enrich_error": None, "enrich_source": found["source_url"] or None}
    for f in ("image_url", "description", "description_en"):
        if not bike.get(f) and found[f]:
            upd[f] = found[f]
    specs = bike.get("specs") or {}
    for f, v in found["specs"].items():
        if not specs.get(f):
            upd[f"specs.{f}"] = v
    await db.bikes.update_one({"id": bike_id}, {"$set": upd})
    updated = [k for k in upd if not k.startswith("enrich")]
    logger.info("Enriched %s: fields=%s", model, updated)
    return {"ok": True, "photo": "image_url" in upd, "updated": updated}


async def enrich_new_bikes(db):
    """Enrich sheet models never processed that are missing a photo or a description."""
    todo = await db.bikes.find({"sheet_model": {"$exists": True}, "enriched_at": {"$exists": False},
                                "$or": [{"image_url": ""}, {"image_url": None}, {"description": ""}]},
                               {"_id": 0, "id": 1}).to_list(20)
    for b in todo:
        await enrich_bike(db, b["id"])
