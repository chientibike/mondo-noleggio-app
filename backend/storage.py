"""Emergent managed object storage (bike photos)."""
import os

import requests
from starlette.concurrency import run_in_threadpool

# `or`, not a default= argument: the platform sets this to "" when it has no value.
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
APP_NAME = "mondo-noleggio"
_storage_key = None


def init_storage() -> str:
    """Idempotent: returns a reusable storage_key."""
    global _storage_key
    if _storage_key:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": os.environ["EMERGENT_LLM_KEY"]}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def _with_key(call):
    """Run a storage call; on 503 (stale key) re-init once and retry."""
    global _storage_key
    resp = call(init_storage())
    if resp.status_code == 503:
        _storage_key = None
        resp = call(init_storage())
    resp.raise_for_status()
    return resp


def _put(path: str, data: bytes, content_type: str) -> dict:
    return _with_key(lambda k: requests.put(f"{STORAGE_URL}/objects/{path}", data=data, timeout=120,
                                            headers={"X-Storage-Key": k, "Content-Type": content_type})).json()


def _get(path: str) -> tuple[bytes, str]:
    resp = _with_key(lambda k: requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": k}, timeout=60))
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


async def put_object(path: str, data: bytes, content_type: str) -> dict:
    return await run_in_threadpool(_put, path, data, content_type)


async def get_object(path: str) -> tuple[bytes, str]:
    return await run_in_threadpool(_get, path)
