"""Single-shot warmup endpoint for the chat shell.

The web client otherwise opens 6–8 parallel SWR requests on every cold mount of
``/chat`` (user, companies, agent, scopes, billing, conversations, active
conversations, presence). Each adds a TLS round trip; on slow connections or
on `/user → /chat` redirects with no warm cache the perceived hang is mostly
this fan-out. Composing the same payload server-side cuts that to one request.

The shape is intentionally a superset of the individual endpoints so the
client can seed each SWR cache key once at app shell mount and individual
hooks become no-ops on first render. Existing endpoints stay live and
unchanged — this is purely additive.
"""

import asyncio
import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, Header, HTTPException

from ApiClient import verify_api_key
from Conversations import Conversations
from MagicalAuth import MagicalAuth
from WorkerRegistry import worker_registry

app = APIRouter()


@app.get(
    "/v1/me/bootstrap",
    summary="Single-shot chat shell warmup",
    description=(
        "Returns user identity + companies + agents + scopes + recent "
        "conversations + counts + active conversations + billing flag in one "
        "call. Replaces the 6–8 parallel SWR requests the chat page fires on "
        "cold mount. Safe to call repeatedly — composes existing read-only "
        "endpoints with no side effects."
    ),
    tags=["Bootstrap"],
    dependencies=[Depends(verify_api_key)],
)
async def me_bootstrap(
    user=Depends(verify_api_key),
    authorization: str = Header(None),
    recent_limit: int = 50,
):
    if recent_limit <= 0:
        recent_limit = 50
    if recent_limit > 200:
        recent_limit = 200

    auth = MagicalAuth(token=authorization)

    payload: Dict[str, Any] = {}
    section_timings: Dict[str, float] = {}

    def _slim_companies(companies):
        """Strip the heaviest fields (per-agent commands, base64 icon_url)
        from the bundle. Cuts the chat-shell payload roughly in half on
        accounts with multiple companies × agents — chat doesn't need
        commands until the user actually opens an agent picker, and the
        full /v1/user fetch that the client SWR fires a moment later
        carries everything for consumers that do."""
        slim_list = []
        for c in companies or []:
            if not isinstance(c, dict):
                slim_list.append(c)
                continue
            slim = {k: v for k, v in c.items() if k != "icon_url"}
            agents = slim.get("agents")
            if isinstance(agents, list):
                slim["agents"] = [
                    (
                        {ak: av for ak, av in a.items() if ak != "commands"}
                        if isinstance(a, dict)
                        else a
                    )
                    for a in agents
                ]
            slim_list.append(slim)
        return slim_list

    def _load_user_bundle():
        t0 = time.perf_counter()
        bundle = auth.get_user_data_optimized()
        section_timings["user_bundle"] = (time.perf_counter() - t0) * 1000
        return bundle

    def _load_conversations():
        t0 = time.perf_counter()
        c = Conversations(user=user)
        convs = c.get_conversations_with_detail(limit=recent_limit, offset=0) or {}
        section_timings["recent_conversations"] = (time.perf_counter() - t0) * 1000
        return convs

    def _load_counts():
        t0 = time.perf_counter()
        c = Conversations(user=user)
        counts = c.get_conversation_counts()
        section_timings["counts"] = (time.perf_counter() - t0) * 1000
        return counts

    def _load_active():
        t0 = time.perf_counter()
        active = worker_registry.get_user_conversations(user_id=auth.user_id) or {}
        for _, info in active.items():
            info.pop("task", None)
        section_timings["active"] = (time.perf_counter() - t0) * 1000
        return active

    def _load_billing():
        t0 = time.perf_counter()
        try:
            from ExtensionsHub import ExtensionsHub
            from Globals import getenv

            if getenv("BILLING_PAUSED", "false").lower() == "true":
                section_timings["billing"] = (time.perf_counter() - t0) * 1000
                return False
            hub = ExtensionsHub()
            try:
                cfg = hub.get_pricing_config()
            except Exception:
                cfg = hub.get_default_pricing_config()
            value = bool(
                cfg.get("billing_enabled", True) if isinstance(cfg, dict) else True
            )
            section_timings["billing"] = (time.perf_counter() - t0) * 1000
            return value
        except Exception:
            section_timings["billing"] = (time.perf_counter() - t0) * 1000
            return None

    # All five sections are independent — they each open their own DB session
    # internally — so we can run them in parallel via threadpool. On the
    # 11k-conversation account this reduces total latency from
    # max(t_user, t_conv, t_counts, ...) summed sequentially to the slowest
    # branch alone (typically the conversations fetch).
    overall_t0 = time.perf_counter()
    try:
        (
            user_bundle,
            recent_conversations,
            counts,
            active,
            billing_enabled,
        ) = await asyncio.gather(
            asyncio.to_thread(_load_user_bundle),
            asyncio.to_thread(_load_conversations),
            asyncio.to_thread(_load_counts),
            asyncio.to_thread(_load_active),
            asyncio.to_thread(_load_billing),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logging.error(f"bootstrap: parallel load failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to assemble bootstrap.")
    section_timings["total_parallel"] = (time.perf_counter() - overall_t0) * 1000

    user_record = user_bundle["user"]
    preferences = user_bundle.get("preferences", {})
    payload["user"] = {
        "id": auth.user_id,
        "email": user_record.email,
        "first_name": user_record.first_name,
        "last_name": user_record.last_name,
        "username": getattr(user_record, "username", None),
        "avatar_url": getattr(user_record, "avatar_url", None),
        "last_seen": (
            user_record.last_seen.isoformat()
            if getattr(user_record, "last_seen", None)
            else None
        ),
        "status_text": getattr(user_record, "status_text", None),
        "tos_accepted_at": (
            user_record.tos_accepted_at.isoformat()
            if user_record.tos_accepted_at
            else None
        ),
        **preferences,
    }
    payload["companies"] = _slim_companies(user_bundle.get("companies", []))
    payload["recent_conversations"] = recent_conversations
    payload["conversations_total"] = (counts or {}).get("total", 0)
    payload["conversations_pinned_count"] = (counts or {}).get("pinned", 0)
    payload["conversations_unread_count"] = (counts or {}).get("unread", 0)
    payload["conversations_by_agent"] = (counts or {}).get("by_agent", {})
    payload["active_conversations"] = active
    payload["billing_enabled"] = billing_enabled

    logging.info(f"bootstrap timings (ms): {section_timings}")
    return payload
