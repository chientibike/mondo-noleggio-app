"""Rental contract read from the "contratto noleggio" tab of the Google Sheet."""
import csv
import hashlib
import io
import logging
import os
import time
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)
TAB = "contratto noleggio"
CACHE_SECONDS = 600
_cache: dict = {"at": 0.0, "doc": None}


def parse_contract(text: str) -> list[str]:
    """One line per sheet row: non-empty cells joined (label/value pairs stay on one line)."""
    lines = []
    for row in csv.reader(io.StringIO(text)):
        cells = [c.strip() for c in row if c and c.strip()]
        if cells:
            lines.append("  ".join(cells))
    return lines


async def get_contract(db) -> dict:
    """{version, lines, updated_at}. Cached 10 min; falls back to the last saved copy if the sheet is unreachable."""
    if _cache["doc"] and time.time() - _cache["at"] < CACHE_SECONDS:
        return _cache["doc"]
    url = f"https://docs.google.com/spreadsheets/d/{os.environ['SHEET_ID']}/gviz/tq?tqx=out:csv&sheet={quote(TAB)}"
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
            r = await c.get(url)
        lines = parse_contract(r.text) if r.status_code == 200 else []
        if len(lines) < 3:
            raise RuntimeError(f"contratto non leggibile (HTTP {r.status_code})")
        version = hashlib.sha256("\n".join(lines).encode()).hexdigest()[:16]
        await db.contracts.update_one({"version": version}, {"$setOnInsert": {
            "version": version, "lines": lines, "created_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
        doc = {"version": version, "lines": lines}
    except Exception as e:
        logger.warning("Contract fetch failed: %s", e)
        last = await db.contracts.find_one({}, {"_id": 0, "version": 1, "lines": 1}, sort=[("created_at", -1)])
        if not last:
            raise
        doc = last
    _cache.update(at=time.time(), doc=doc)
    return doc
