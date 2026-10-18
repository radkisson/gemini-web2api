"""Model definitions and mapping from Gemini frontend JS source."""
import json
import re
import uuid

from .config import CONFIG

# MODE_CATEGORY enum from 028-6eb337387583.js:
#   1=FAST, 2=THINKING, 3=PRO, 4=AUTO, 5=FAST_DYNAMIC_THINKING, 6=FLASH_LITE
#
# The mode/think fields alone only select a *request shape*: ticket-less
# requests are all served the account default (measured: "3.5 Flash-Lite" for
# every mode). Which model actually answers is chosen by the
# X-Goog-Ext-525001261-Jspb "model ticket" header, hence `ticket`/`variant`
# below. Tickets are per-model and Google rotates them; override per model with
# config.json "model_tickets": {"<model>": "<16 hex chars>"}.

MODELS = {
    "gemini-3.7-flash": {
        "mode": 1, "think": 4,
        "ticket": "56fdd199312815e2", "variant": 1,
        "desc": "Latest all-around model (Gemini 3.7 Flash)",
    },
    # The backend self-labels its flash tier "3.8 Flash" and upstream PRs #91/#101
    # add these names; both map to coordinates that already existed, so they are
    # aliases, not a distinct backend model.
    "gemini-3.8-flash": {
        "mode": 1, "think": 4,
        "ticket": "56fdd199312815e2", "variant": 1,
        "desc": "Alias for the default flash tier (same mode/think as 3.7 Flash)",
    },
    "gemini-3.8-flash-thinking": {
        "mode": 2, "think": 0,
        "desc": "Alias for gemini-3.5-flash-thinking (deep thinking tier)",
    },
    "gemini-3.6-flash": {
        "mode": 1, "think": 4,
        "ticket": "56fdd199312815e2", "variant": 1,
        "desc": "All-around model (Gemini 3.6 Flash)",
    },
    "gemini-3.5-flash": {
        "mode": 1, "think": 4,
        "ticket": "56fdd199312815e2", "variant": 1,
        "desc": "Alias for gemini-3.6-flash (backend upgraded)",
    },
    "gemini-3.5-flash-thinking": {
        "mode": 2, "think": 0,
        "desc": "Deep thinking mode, longest output (~20k chars)",
    },
    "gemini-3.1-pro": {
        "mode": 3, "think": 4,
        "ticket": "e6fa609c3fa255c0", "variant": 1,
        "desc": "Pro model (requires cookie for real routing)",
    },
    "gemini-3.1-pro-enhanced": {
        "mode": 3, "think": 4, "extra": {31: 2, 80: 3},
        "ticket": "e6fa609c3fa255c0", "variant": 1,
        "desc": "Pro with enhanced output (experimental)",
    },
    "gemini-auto": {
        "mode": 4, "think": 4,
        "desc": "Auto model selection",
    },
    "gemini-3.5-flash-thinking-lite": {
        "mode": 5, "think": 0,
        "desc": "Dynamic thinking with adaptive depth",
    },
    "gemini-flash-lite": {
        "mode": 6, "think": 4,
        "ticket": "8c46e95b1a07cecc", "variant": 1,
        "desc": "Lightweight fast model",
    },
}


def build_model_ticket(cfg: dict, model_name: str = None, variant_override: int = None,
                      model_tickets: dict = None):
    """Build the X-Goog-Ext-525001261-Jspb header value for StreamGenerate.

    Element [4] is the ticket id, [14] the mode and [15] the variant; the rest
    is fixed scaffolding copied from the web client's request.
    """
    if model_tickets is None:
        model_tickets = CONFIG.get("model_tickets") or {}
    base = re.sub(r"-(low|medium|high)$", "", model_name or "")
    ticket = model_tickets.get(model_name) or model_tickets.get(base) or cfg.get("ticket")
    if not ticket:
        return None
    variant = variant_override if variant_override is not None else cfg.get("variant", 1)
    arr = [
        1, None, None, None, ticket, None, None, 0,
        [4, 5, 6, 8, 4, 5, 6, 8],
        None, None, 2, None, None,
        cfg["mode"], variant, str(uuid.uuid4()),
    ]
    return json.dumps(arr, separators=(",", ":"))


def resolve_model(model_name: str, default: str = "gemini-3.6-flash"):
    """Resolve model name to (name, mode_id, think_mode, error, extra_fields).

    Unknown model names fall back to default rather than erroring,
    since upstream clients may request arbitrary model identifiers.
    """
    think_override = None
    if "@think=" in model_name:
        model_name, think_str = model_name.rsplit("@think=", 1)
        try:
            think_override = int(think_str)
        except ValueError:
            return None, None, None, f"Invalid think level: {think_str}", None
    cfg = MODELS.get(model_name)
    if not cfg:
        from .gemini import log
        log(f"Unknown model '{model_name}', falling back to '{default}'")
        model_name = default
        cfg = MODELS[default]
    mode_id = cfg["mode"]
    think_mode = think_override if think_override is not None else cfg["think"]
    extra = dict(cfg.get("extra") or {})
    ticket = build_model_ticket(cfg, model_name)
    if ticket:
        extra["_ticket"] = ticket
    return model_name, mode_id, think_mode, None, (extra or None)
