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

PROMPT = """Search the web for the bike model "{model}" ({hint}).
Use the manufacturer's official product page as the main source (retailers only to fill gaps).
Reply with ONLY a JSON object, no markdown:
{{"name": official model name,
 "description_it": 2 short sentences in Italian for customers renting it (what it is, where it shines),
 "description_en": same in English,
 "specs": {{"frame": "", "motor": "", "battery": "", "range": "", "suspension": "", "groupset": "", "brakes": "", "wheels": "", "weight": ""}},
 "pages": [up to 5 product page URLs you actually found, official first],
 "images": [direct product photo URLs you actually found, if any]}}
Each spec is one short line; use "" when not stated in sources or not applicable (e.g. motor/battery/range for non-electric bikes).
Never invent URLs."""


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    return json.loads(m.group(0)) if m else {}


async def _research(model: str, category: str) -> tuple[dict, list]:
    chat = (LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=f"enrich-{model}",
                    system_message="You are a precise bicycle specification researcher.")
            .with_model("gemini", "gemini-2.5-flash").with_tools([{"googleSearch": {}}]))
    r = await chat.send_message_with_tools(UserMessage(text=PROMPT.format(model=model, hint=CATEGORY_HINT.get(category, "bike"))))
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


async def _find_photo(images: list, pages: list, brand: str = "") -> tuple[Optional[str], Optional[str]]:
    """Return (photo_url, source_page_url): first verified image from direct candidates or page meta tags.
    Pages are resolved first so the manufacturer's own site (host containing the brand) is preferred."""
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
        for url in images:
            if await _is_photo(c, url):
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
            for rx in META_IMG:
                for img in rx.findall(r.text)[:3]:
                    img = img.replace("&amp;", "&")
                    if await _is_photo(c, img):
                        return img, str(r.url)
    return None, None


async def enrich_bike(db, bike_id: str, force: bool = False) -> dict:
    """Fill only the empty fields of a bike (photo, descriptions, specs). Never overwrites admin data."""
    bike = await db.bikes.find_one({"id": bike_id}, {"_id": 0})
    if not bike or (bike.get("enriched_at") and not force):
        return {"ok": False, "reason": "skipped"}
    await db.bikes.update_one({"id": bike_id}, {"$set": {"enriched_at": datetime.now(timezone.utc).isoformat()}})
    model = bike.get("sheet_model") or bike["name"]
    try:
        info, grounded = await _research(model, bike["category"])
    except Exception as e:
        logger.warning("Enrich research failed for %s: %s", model, e)
        await db.bikes.update_one({"id": bike_id}, {"$set": {"enrich_error": str(e)[:200]}})
        return {"ok": False, "reason": "research_failed"}
    pages = [u for u in (info.get("pages") or []) if isinstance(u, str)] + grounded
    photo, page = (None, None)
    brand = model.split()[0].lower() if model.split() else ""
    if not bike.get("image_url"):
        photo, page = await _find_photo([u for u in (info.get("images") or []) if isinstance(u, str)], pages, brand)
        if not photo:  # search results vary between runs: one more attempt
            try:
                info2, grounded2 = await _research(model, bike["category"])
                pages += [u for u in (info2.get("pages") or []) if isinstance(u, str)] + grounded2
                photo, page = await _find_photo([u for u in (info2.get("images") or []) if isinstance(u, str)], pages, brand)
            except Exception as e:
                logger.warning("Enrich retry failed for %s: %s", model, e)

    upd = {"enrich_error": None, "enrich_source": page or (pages[0] if pages else None)}
    if photo:
        upd["image_url"] = photo
    for f in ("description_it", "description_en"):
        target = "description" if f == "description_it" else f
        if not bike.get(target) and isinstance(info.get(f), str) and info[f].strip():
            upd[target] = info[f].strip()
    specs = bike.get("specs") or {}
    for f in SPEC_FIELDS:
        v = (info.get("specs") or {}).get(f)
        if not specs.get(f) and isinstance(v, str) and v.strip():
            upd[f"specs.{f}"] = v.strip()
    await db.bikes.update_one({"id": bike_id}, {"$set": upd})
    logger.info("Enriched %s: photo=%s fields=%s", model, bool(photo), [k for k in upd if not k.startswith("enrich")])
    return {"ok": True, "photo": bool(photo), "updated": [k for k in upd if not k.startswith("enrich")]}


async def enrich_new_bikes(db):
    """Enrich sheet models never processed that are missing a photo or a description."""
    todo = await db.bikes.find({"sheet_model": {"$exists": True}, "enriched_at": {"$exists": False},
                                "$or": [{"image_url": ""}, {"image_url": None}, {"description": ""}]},
                               {"_id": 0, "id": 1}).to_list(20)
    for b in todo:
        await enrich_bike(db, b["id"])
