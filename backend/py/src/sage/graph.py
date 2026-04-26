"""LangGraph supervisor for Sage.

Routes a single utterance through:
    supervisor → {memory_lookup, browser_agent, responder} → responder → END

Each node pushes a trace event to the Node bridge so the Electron orb can
render the reasoning live. The browser_agent is a thin HTTP shim onto Node's
Stagehand singleton at /internal/browser-task.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from openai import OpenAI

log = logging.getLogger("sage.graph")

ROUTING_MODEL = "gpt-4.1-mini"
RESPONDER_MODEL = "gpt-4.1-mini"

BRIDGE_URL = os.getenv("BRIDGE_URL", "http://localhost:3001")

_openai_client: OpenAI | None = None


def get_openai() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _openai_client


class SageState(TypedDict, total=False):
    session_id: str
    patient_id: str
    user_text: str
    intent: str
    intent_reason: str
    payload_goal: str
    profile: dict[str, Any]
    memory_summary: str
    browser_result: dict[str, Any]
    response_text: str
    trace: list[dict[str, Any]]


def _push_trace(state: SageState, node: str, text: str) -> None:
    entry = {"node": node, "text": text}
    state.setdefault("trace", []).append(entry)
    session_id = state.get("session_id")
    if not session_id:
        return
    try:
        httpx.post(
            f"{BRIDGE_URL}/internal/trace",
            json={"session_id": session_id, "node": node, "text": text},
            timeout=2.0,
        )
    except Exception as err:
        log.debug("trace push failed (%s) — bridge may be offline", err)


# ─── nodes ────────────────────────────────────────────────────────────────────

SUPERVISOR_SYSTEM = """You are Sage's intent router. Classify the user utterance.

Return ONLY a JSON object: {"intent": <one of>, "reason": <one short clause>, "goal": <optional product/task phrase>}.

Intents:
- "browser_task" — the user wants a real-world task done that needs a browser (ordering items, refilling things, finding products on a real site). Set "goal" to the cleaned product or task phrase, e.g. "weekly pill organizer 7 day".
- "memory_lookup" — the user is asking about their own life, doctors, appointments, address, pharmacy, things they "usually" do, or who their caregiver is. Goal can be empty.
- "smalltalk" — greeting, thanks, casual chit-chat, vague check-ins.
- "end_session" — explicit "I'm done", "goodbye", "that's all".

Examples:
user: "I need one of those weekly pill organizers" → {"intent":"browser_task","reason":"product order","goal":"weekly pill organizer 7 day"}
user: "When do I need to see Dr. Mehta?" → {"intent":"memory_lookup","reason":"doctor appointment","goal":""}
user: "Hi Sage, how are you?" → {"intent":"smalltalk","reason":"greeting","goal":""}
user: "Okay I think we're done." → {"intent":"end_session","reason":"goodbye","goal":""}
"""


def supervisor_node(state: SageState) -> SageState:
    text = state.get("user_text", "")
    client = get_openai()
    resp = client.chat.completions.create(
        model=ROUTING_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SUPERVISOR_SYSTEM},
            {"role": "user", "content": text},
        ],
        temperature=0.0,
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"intent": "smalltalk", "reason": "fallback parse"}

    intent = data.get("intent", "smalltalk")
    if intent not in {"browser_task", "memory_lookup", "smalltalk", "end_session"}:
        intent = "smalltalk"
    goal = (data.get("goal") or "").strip()
    reason = (data.get("reason") or "").strip()

    update: SageState = {"intent": intent, "intent_reason": reason, "payload_goal": goal}
    state.update(update)
    _push_trace(state, "supervisor", f"intent={intent} ({reason})")
    return update


MEMORY_SYSTEM = """You are matching a user utterance to a structured patient profile.

Return ONLY a JSON object: {"match": <profile field path or empty>, "summary": <one warm sentence>}.

The profile keys are: doctors[], appointments[], pharmacy, address, common_items[], caregiver.

Examples:
profile: {"appointments":[{"doctor":"Dr. Mehta","when":"Thursday 9:00am","address":"450 Maple Ave"}]}
user: "When do I need to see Dr. Mehta?"
→ {"match":"appointments[0]","summary":"Your appointment with Dr. Mehta is Thursday at 9 a.m. at 450 Maple Ave."}

profile: {"pharmacy":{"name":"CVS Maple","address":"410 Maple Ave"}}
user: "Where do I usually pick up prescriptions?"
→ {"match":"pharmacy","summary":"You usually pick up prescriptions at CVS Maple on 410 Maple Ave."}

If nothing matches, return {"match":"","summary":""}. Never invent a fact that is not in the profile.
"""


def memory_lookup_node(state: SageState) -> SageState:
    from sage import snowflake_io  # local import — avoids load-order issues

    patient_id = state.get("patient_id") or "p_eleanor"
    profile = state.get("profile")
    if profile is None:
        try:
            profile = snowflake_io.get_profile(patient_id)
        except Exception as err:
            log.warning("profile load failed for %s: %s", patient_id, err)
            profile = None

    if not profile:
        _push_trace(state, "memory_lookup", f"no profile for {patient_id}")
        return {"memory_summary": "", "profile": {}}

    user_text = state.get("user_text", "")
    profile_for_prompt = {k: v for k, v in profile.items() if k != "patient_id"}

    client = get_openai()
    resp = client.chat.completions.create(
        model=ROUTING_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": MEMORY_SYSTEM},
            {
                "role": "user",
                "content": f"profile: {json.dumps(profile_for_prompt)}\nuser: {user_text}",
            },
        ],
        temperature=0.0,
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"match": "", "summary": ""}

    summary = (data.get("summary") or "").strip()
    match = (data.get("match") or "").strip()
    _push_trace(state, "memory_lookup", f"match={match or 'none'}")
    return {"memory_summary": summary, "profile": profile}


def browser_agent_node(state: SageState) -> SageState:
    goal = state.get("payload_goal") or state.get("user_text", "")
    _push_trace(state, "browser_agent", f"opening amazon for: {goal[:80]}")
    try:
        with httpx.Client(timeout=45.0) as client:
            r = client.post(
                f"{BRIDGE_URL}/internal/browser-task",
                json={"goal": goal, "session_id": state.get("session_id")},
            )
            r.raise_for_status()
            data = r.json()
    except Exception as err:
        log.warning("browser-task failed: %s", err)
        data = {"ok": False, "reason": str(err)}

    state["browser_result"] = data
    if data.get("ok"):
        _push_trace(state, "browser_agent", f"found: {data.get('title', '')[:80]}")
    else:
        _push_trace(state, "browser_agent", f"failed: {data.get('reason', 'unknown')}")
    return {"browser_result": data}


RESPONDER_SYSTEM = """You are Sage — a warm, calm, dignified voice assistant for an older adult.

Hard rules:
- Keep replies under 80 words. Spoken aloud, so prefer short clean sentences.
- Never robotic ("Processing…", "Task complete"). Speak like a kind helper.
- If a browser task succeeded, name what was found and the price plainly.
- If a browser task failed, do NOT panic the user. Offer a graceful next step.
- If the user is just chatting, respond briefly and warmly without forcing a task.
- Never claim a medical diagnosis. Never use the word "monitoring".
"""


def responder_node(state: SageState) -> SageState:
    user_text = state.get("user_text", "")
    intent = state.get("intent", "smalltalk")
    browser_result = state.get("browser_result") or {}
    memory_summary = state.get("memory_summary") or ""

    context_parts = [f"User said: {user_text}", f"Intent: {intent}"]
    if memory_summary:
        context_parts.append(f"Memory: {memory_summary}")
    if browser_result:
        if browser_result.get("ok"):
            context_parts.append(
                f"Browser result: title='{browser_result.get('title')}', price='{browser_result.get('price')}'"
            )
        else:
            context_parts.append(f"Browser failed: {browser_result.get('reason')}")

    client = get_openai()
    resp = client.chat.completions.create(
        model=RESPONDER_MODEL,
        messages=[
            {"role": "system", "content": RESPONDER_SYSTEM},
            {"role": "user", "content": "\n".join(context_parts)},
        ],
        temperature=0.6,
        max_tokens=180,
    )
    text = (resp.choices[0].message.content or "").strip()
    _push_trace(state, "responder", "reply ready")
    return {"response_text": text}


# ─── graph wiring ─────────────────────────────────────────────────────────────


def _route(state: SageState) -> str:
    intent = state.get("intent", "smalltalk")
    if intent == "browser_task":
        return "browser_agent"
    if intent == "memory_lookup":
        return "memory_lookup"
    return "responder"


def build_graph():
    sg = StateGraph(SageState)
    sg.add_node("supervisor", supervisor_node)
    sg.add_node("memory_lookup", memory_lookup_node)
    sg.add_node("browser_agent", browser_agent_node)
    sg.add_node("responder", responder_node)

    sg.add_edge(START, "supervisor")
    sg.add_conditional_edges(
        "supervisor",
        _route,
        {
            "memory_lookup": "memory_lookup",
            "browser_agent": "browser_agent",
            "responder": "responder",
        },
    )
    sg.add_edge("memory_lookup", "responder")
    sg.add_edge("browser_agent", "responder")
    sg.add_edge("responder", END)
    return sg.compile()


_compiled = None


def get_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled


def run_turn(session_id: str, text: str) -> dict:
    """Synchronous one-turn convenience wrapper."""
    initial: SageState = {
        "session_id": session_id,
        "patient_id": session_id.split(":", 1)[0] if ":" in session_id else session_id,
        "user_text": text,
        "trace": [],
    }
    final_state = get_graph().invoke(initial)
    return {
        "response_text": final_state.get("response_text", ""),
        "trace": final_state.get("trace", []),
        "intent": final_state.get("intent"),
        "browser_result": final_state.get("browser_result"),
    }
