"""Input guardrails - runs before any LLM sees the message (layer 3 "AI control plane").

1. PII masking: card numbers, Aadhaar, PAN, phone numbers and emails typed by the user
   are replaced with placeholders, so they are never sent to the LLM provider or stored
   in traces. The banking tools don't need them - the customer is known from the login.
2. Prompt-injection screening: messages trying to override the assistant's instructions
   or access other customers are refused without calling the LLM.

These are deliberately simple, transparent regex rules. Production systems layer
ML classifiers (e.g. a PII NER model or an LLM-based safety judge) on top.
"""
import re
from dataclasses import dataclass, field

PII_PATTERNS = [
    ("CARD_NUMBER", re.compile(r"\b(?:\d[ -]?){15}\d\b")),
    ("AADHAAR", re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("PHONE", re.compile(r"(?:\+91[ -]?)?\b[6-9]\d{9}\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")),
    ("OTP_OR_PIN", re.compile(r"\b(?:otp|pin|cvv|password)\b\D{0,12}\d{3,8}\b", re.IGNORECASE)),
]

INJECTION_PATTERNS = [
    r"ignore (?:all |any |the )?(?:previous|prior|above) (?:instructions|rules|prompts?)",
    r"disregard (?:your|the|all) (?:instructions|rules|guidelines)",
    r"(?:reveal|show|print|repeat) (?:me )?(?:your|the) (?:system )?(?:prompt|instructions)",
    r"you are now (?:in )?(?:developer|dan|admin|god) mode",
    r"(?:act|pretend) as (?:an? )?(?:admin|administrator|bank employee|developer)",
    r"(?:other|another|different) customer'?s? (?:account|data|balance|transactions|details)",
    r"customer[_ ]?id\s*[:=]?\s*\d+",
    r"(?:drop|delete|truncate) table",
]
_INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)

MAX_INPUT_CHARS = 2000

REFUSAL = ("I can't help with that request. I can only access your own SmartBank accounts and "
           "follow the bank's security policies. Try asking about your balance, transactions, "
           "card security or loan eligibility.")


@dataclass
class GuardrailResult:
    text: str                       # message after PII masking
    allowed: bool = True
    reason: str | None = None
    pii_found: list[str] = field(default_factory=list)


def check_input(text: str) -> GuardrailResult:
    text = text.strip()
    if not text:
        return GuardrailResult(text, allowed=False, reason="empty_message")
    if len(text) > MAX_INPUT_CHARS:
        return GuardrailResult(text[:MAX_INPUT_CHARS], allowed=False, reason="message_too_long")

    masked, found = text, []
    for label, pattern in PII_PATTERNS:
        if pattern.search(masked):
            found.append(label)
            masked = pattern.sub(f"[{label}_REDACTED]", masked)

    if _INJECTION_RE.search(text):
        return GuardrailResult(masked, allowed=False, reason="prompt_injection", pii_found=found)
    return GuardrailResult(masked, pii_found=found)
