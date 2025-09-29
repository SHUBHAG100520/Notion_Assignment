
from __future__ import annotations
import json, os, re
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

def _load_json(name: str) -> Any:
    with open(DATA_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)

def parse_iso(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)

def utcnow() -> datetime:
    now_env = os.getenv("NOW_ISO")
    if now_env:
        return parse_iso(now_env)
    return datetime.now(timezone.utc)

def product_search(query: str = "", price_max: Optional[float] = None, tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    items = _load_json("products.json")
    q = (query or "").lower()
    tokens = [t for t in re.findall(r"[a-z0-9]+", q) if t]
    def matches(item):
        if price_max is not None and item["price"] > price_max:
            return False
        if tags:
            tagset = set([t.lower() for t in tags])
            if not tagset.issubset(set([t.lower() for t in item.get("tags",[])])):
                return False
            return True  # tag match is sufficient
        if tokens:
            hay = " ".join([item["title"], " ".join(item.get("tags",[])), item.get("color","")]).lower()
            meaningful = [tok for tok in tokens if tok not in {"under","less","budget","m","l","xl","s","eta","to","guest","between","im","i","zip"}]
            return any(tok in hay for tok in meaningful) if meaningful else True
        return True
    filtered = [it for it in items if matches(it)]
    filtered.sort(key=lambda x: (x["price"], x["id"]))
    return filtered

def size_recommender(user_inputs: str) -> Dict[str, Any]:
    text = (user_inputs or "").lower()
    rec = "M"
    rationale = "You mentioned you're between M and L; we suggest M for a closer fit or L if you prefer a roomier feel."
    if "loose" in text or "oversized" in text:
        rec = "L"
        rationale = "You prefer a looser fit; L should feel roomier. Choose M for a snugger fit."
    return {"recommended": rec, "rationale": rationale}

def eta(zip_code: str) -> Dict[str, Any]:
    z = str(zip_code)
    if z.startswith("56"):
        window = "3–5 business days"
    elif z.startswith(("10","11","12")):
        window = "2–3 business days"
    else:
        window = "2–5 business days"
    return {"zip": z, "eta_window": window}

def order_lookup(order_id: str, email: str) -> Optional[Dict[str, Any]]:
    orders = _load_json("orders.json")
    for o in orders:
        if o["order_id"].lower() == order_id.lower() and o["email"].lower() == email.lower():
            return o
    return None

def order_cancel(order_id: str, timestamp_iso: Optional[str] = None) -> Dict[str, Any]:
    orders = _load_json("orders.json")
    order = next((o for o in orders if o["order_id"].lower() == order_id.lower()), None)
    if not order:
        return {"cancel_allowed": False, "reason": "order_not_found"}
    created = parse_iso(order["created_at"])
    now = parse_iso(timestamp_iso) if timestamp_iso else utcnow()
    delta = (now - created).total_seconds() / 60.0
    if delta <= 60.0 + 1e-9:
        return {"cancel_allowed": True, "reason": f"within_60_min ({delta:.1f} min)"}
    return {"cancel_allowed": False, "reason": f">60 min ({delta:.1f} min)"}