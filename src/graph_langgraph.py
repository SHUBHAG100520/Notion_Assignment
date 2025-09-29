
from __future__ import annotations
from typing import TypedDict, List, Dict, Any, Optional
import os, re, json
from pydantic import BaseModel, Field
from datetime import datetime
# LangGraph
from langgraph.graph import StateGraph, END

# Local tools
try:
    from . import tools
except Exception:
    import tools

# ---------- LLM helper ----------
import os

def use_llm() -> bool:
    # Use an LLM if either OpenAI or Gemini key is set and mock is OFF
    has_any_key = bool(os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY"))
    return has_any_key and not os.getenv("USE_MOCK_LLM")

def call_llm(system: str, user: str) -> str:
    provider = (os.getenv("PROVIDER") or "").lower()
    if provider == "gemini" or os.getenv("GEMINI_API_KEY"):
        # ---------- Google Gemini ----------
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        model = genai.GenerativeModel(model_name)
        # Gemini has no separate "system" role; prefix system rules to the prompt.
        prompt = f"{system.strip()}\n\nUser:\n{user.strip()}"
        resp = model.generate_content(prompt)
        # Handle both text and potential empty parts safely
        return (resp.text or "").strip()
    else:
        # ---------- OpenAI (default) ----------
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role":"system","content":system},{"role":"user","content":user}],
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()


# ---------- State ----------
class AgentState(TypedDict, total=False):
    prompt: str
    intent: str
    tools_called: List[str]
    evidence: List[Dict[str, Any]]
    policy_decision: Dict[str, Any] | None
    final_message: str
    # working fields
    order: Dict[str, Any] | None
    order_id: str | None
    email: str | None
    products: List[Dict[str, Any]]
    size: Dict[str, Any]
    eta: Dict[str, Any]

SYSTEM = """You are EvoAI Agent. Follow policy strictly: product assist vs order help, 60-min cancel rule, no fake discounts. Be concise."""

# ---------- Nodes ----------
def router_node(state: AgentState) -> AgentState:
    p = state["prompt"]
    if use_llm():
        text = call_llm(SYSTEM, f"Classify into one of: product_assist, order_help, other\nUser: {p}")
        intent = "product_assist" if "product" in text else "order_help" if "order" in text else "other"
    else:
        low = p.lower()
        if any(k in low for k in ["cancel order", "order status", "order help", "where is my order", "order ", "refund"]):
            intent = "order_help"
        elif any(k in low for k in ["dress","product","wedding","midi","size","eta","zip"]):
            intent = "product_assist"
        else:
            intent = "other"
    state["intent"] = intent
    state["tools_called"] = []
    state["evidence"] = []
    return state

def tool_selector_node(state: AgentState) -> AgentState:
    intent = state["intent"]
    prompt = state["prompt"]
    tools_called = state["tools_called"]

    if intent == "product_assist":
        price_cap = None
        m = re.search(r"under\s*\$?\s*(\d+)", prompt.lower())
        if m: price_cap = float(m.group(1))
        tags = []
        if "wedding" in prompt.lower(): tags.append("wedding")
        if "midi" in prompt.lower(): tags.append("midi")
        products = tools.product_search(prompt, price_cap, tags or None)
        tools_called.append("product_search")

        size = tools.size_recommender(prompt); tools_called.append("size_recommender")
        zm = re.search(r"(\b\d{5,6}\b)", prompt)
        eta = tools.eta(zm.group(1) if zm else "00000"); tools_called.append("eta")
        picks = products[:2]
        state["products"] = picks
        state["size"] = size
        state["eta"] = eta
        state["evidence"].extend([{"id": p["id"], "title": p["title"], "price": p["price"], "sizes": p["sizes"]} for p in picks])

    elif intent == "order_help":
        mo = re.search(r"(?:order\s*)?([A-Za-z]\d{4,})", prompt)
        me = re.search(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", prompt)
        oid = mo.group(1) if mo else None
        email = me.group(1) if me else None
        order = tools.order_lookup(oid, email) if (oid and email) else None
        tools_called.append("order_lookup")
        state["order_id"] = oid; state["email"] = email; state["order"] = order
        state["evidence"].append({"order_id": oid, "email": email, "found": bool(order)})

    state["tools_called"] = tools_called
    return state

def policy_guard_node(state: AgentState) -> AgentState:
    if state["intent"] != "order_help":
        state["policy_decision"] = None
        return state
    order = state.get("order")
    if not order:
        state["policy_decision"] = {"cancel_allowed": False, "reason":"order_not_found_or_missing_credentials"}
        return state
    decision = tools.order_cancel(order["order_id"])
    state["policy_decision"] = decision
    return state

def responder_node(state: AgentState) -> AgentState:
    intent = state["intent"]
    if use_llm():
        # LLM composes final message with structured state context
        context = json.dumps({
            "intent": intent,
            "evidence": state.get("evidence", []),
            "policy_decision": state.get("policy_decision"),
            "products": state.get("products"),
            "size": state.get("size"),
            "eta": state.get("eta"),
            "order": state.get("order"),
        }, indent=2)
        instruction = (
            "Compose the final user reply. Do not invent facts; only use fields in context. "
            "If product_assist: list up to 2 items with title, price, sizes; give size tip and ETA. "
            "If order_help and cancel_allowed: confirm cancellation. "
            "If blocked: explain 60-min policy and offer at least two alternatives. "
            "If other: refuse discount code creation and suggest perks."
        )
        msg = call_llm(SYSTEM, f"{instruction}\n\nContext:\n{context}")
    else:
        # deterministic fallback
        if intent == "product_assist":
            picks = state.get("products", [])
            size = state.get("size", {})
            eta = state.get("eta", {})
            if not picks:
                msg = "I couldn't find items that match your filters. If you can relax the budget or tags, I can search again."
            else:
                lines = [f"• {it['title']} — ${it['price']} | sizes: {', '.join(it['sizes'])}" for it in picks]
                rec = size.get("recommended", "M")
                rationale = size.get("rationale","")
                eta_text = eta.get("eta_window","2–5 business days")
                msg = ("Here are two options under your budget:\n" + "\n".join(lines) +
                       f"\n\nSize tip: go **{rec}**. {rationale}\nETA to {eta.get('zip')}: {eta_text}.")
        elif intent == "order_help":
            decision = state.get("policy_decision", {})
            order = state.get("order")
            if not order:
                msg = "I couldn’t verify that order. Please double-check the order ID and email, or I can hand you to support."
            elif decision.get("cancel_allowed"):
                msg = f"✅ Order {order['order_id']} is cancelled successfully. You’ll see a confirmation email shortly."
            else:
                reason = decision.get("reason", ">60 min")
                msg = (f"❌ I can’t cancel order {order['order_id']} because our policy allows cancellations only within 60 minutes of purchase ({reason}).\n"
                       "Next best options:\n• Edit the delivery address (if the carrier hasn’t picked it up)\n• Convert to store credit after delivery\n• Or I can hand you off to a human agent")
        else:
            msg = ("I can’t generate custom discount codes. You can still save by:\n"
                   "• Joining our newsletter for first-order perks\n• Watching seasonal sales on the site\n• Building a wishlist so we alert you if prices drop")
    state["final_message"] = msg
    return state

def trace_node(state: AgentState) -> AgentState:
    # This node exists so you can introspect state if running LangGraph streaming
    return state

# ---------- Build graph ----------
def build_graph():
    g = StateGraph(AgentState)
    g.add_node("router", router_node)
    g.add_node("tool_selector", tool_selector_node)
    g.add_node("policy_guard", policy_guard_node)
    g.add_node("responder", responder_node)
    g.add_node("trace", trace_node)
    g.set_entry_point("router")
    g.add_edge("router", "tool_selector")
    g.add_edge("tool_selector", "policy_guard")
    g.add_edge("policy_guard", "responder")
    g.add_edge("responder", "trace")
    g.add_edge("trace", END)
    return g.compile()

def run_agent(prompt: str) -> Dict[str, Any]:
    graph = build_graph()
    out = graph.invoke({"prompt": prompt})
    trace = {
        "intent": out.get("intent"),
        "tools_called": out.get("tools_called", []),
        "evidence": out.get("evidence", []),
        "policy_decision": out.get("policy_decision"),
        "final_message": out.get("final_message", ""),
    }
    return {"trace": trace, "reply": out.get("final_message","")}

if __name__ == "__main__":
    res = run_agent("Wedding guest, midi, under $120 — I’m between M/L. ETA to 560001?")
    print(json.dumps(res["trace"], indent=2))
    print("\n" + res["reply"])
