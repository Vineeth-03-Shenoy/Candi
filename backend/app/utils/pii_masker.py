"""
PII Masker

Strips or replaces Personally Identifiable Information before text is
sent to LLMs or written to logs.

Masks:
  - Email addresses          → [EMAIL REDACTED]
  - Phone numbers            → [PHONE REDACTED]
  - Candidate name (resume)  → "You"
  - Interviewer name hints   → [NAME REDACTED]
    (patterns: Mr./Mrs./Ms./Dr. <Name>, "interviewer <Name>", etc.)
"""
import re
from app.utils.logger import get_logger

log = get_logger(__name__)

# ------------------------------------------------------------------
# Compiled patterns
# ------------------------------------------------------------------

_EMAIL = re.compile(
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
    re.IGNORECASE,
)

_PHONE = re.compile(
    r'(\+?1[\s.\-]?)?'                  # optional country code
    r'(\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}'   # US/international 10-digit
    r'|\+?\d[\d\s\-().]{7,14}\d'        # generic international
    r')',
)

# Titles followed by a capitalised word (interviewer name hints in chat)
_TITLED_NAME = re.compile(
    r'\b(Mr\.?|Mrs\.?|Ms\.?|Miss|Dr\.?|Prof\.?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?',
    re.UNICODE,
)

# "interviewer <Name>", "from <Name>", "talked to <Name>"
_INTERVIEWER_HINT = re.compile(
    r'\b(interviewer|recruiter|from|talked\s+to|spoke\s+to|spoke\s+with|contacted\s+by)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
    re.UNICODE,
)


# ------------------------------------------------------------------
# Public helpers
# ------------------------------------------------------------------

def extract_name_from_analysis(analysis_text: str) -> str | None:
    """
    Pull the candidate name out of the LLM's resume analysis output.
    Returns None if not found or explicitly 'not mentioned'.
    """
    match = re.search(
        r'\*\*Candidate Name\*\*[:\s]+([^\n*]+)',
        analysis_text,
        re.IGNORECASE,
    )
    if not match:
        return None
    val = match.group(1).strip().strip("*").strip()
    if val.lower() in {"not mentioned", "not provided", "n/a", "-", "unknown", ""}:
        return None
    log.debug("PII: candidate name extracted from analysis: '%s'", val)
    return val


def mask_pii(text: str, candidate_name: str | None = None) -> str:
    """
    Mask email, phone, and optionally a known candidate name.
    Used for general text (JD, chat messages, etc.).
    """
    if not text:
        return text

    original_len = len(text)

    text = _EMAIL.sub("[EMAIL REDACTED]", text)
    text = _PHONE.sub("[PHONE REDACTED]", text)

    if candidate_name and len(candidate_name) > 1:
        text = re.sub(re.escape(candidate_name), "You", text, flags=re.IGNORECASE)

    if len(text) != original_len:
        log.debug("PII: masked content | original_len=%d → masked_len=%d", original_len, len(text))

    return text


def mask_resume(text: str, candidate_name: str | None = None) -> str:
    """
    Mask PII from a resume.
    Replaces the candidate's name with 'You' and strips email/phone.
    Logs a full masking report including a preview of the masked output.
    """
    if not text:
        return text

    log.info("PII masking resume | original_length=%d chars | candidate_name='%s'",
             len(text), candidate_name or "not provided")

    masked = text

    # Count and replace emails
    emails_found = _EMAIL.findall(masked)
    masked = _EMAIL.sub("[EMAIL REDACTED]", masked)

    # Count and replace phone numbers
    phones_found = _PHONE.findall(masked)
    masked = _PHONE.sub("[PHONE REDACTED]", masked)

    # Count and replace candidate name
    name_occurrences = 0
    if candidate_name and len(candidate_name) > 1:
        name_occurrences = len(re.findall(re.escape(candidate_name), masked, flags=re.IGNORECASE))
        masked = re.sub(re.escape(candidate_name), "You", masked, flags=re.IGNORECASE)

    log.info(
        "PII resume masking complete | "
        "emails_redacted=%d | phones_redacted=%d | name_occurrences_replaced=%d | "
        "original_length=%d | masked_length=%d",
        len(emails_found), len(phones_found), name_occurrences,
        len(text), len(masked),
    )

    if emails_found:
        log.info("PII emails found in resume: %s",
                 [e if isinstance(e, str) else e[0] for e in emails_found])

    # Log masked resume preview (first 600 chars) so the redacted output is visible in the log
    preview = masked[:600].replace("\n", " ").strip()
    log.info("PII masked resume preview (first 600 chars): %s", preview)

    return masked


def mask_chat_message(text: str) -> str:
    """
    Mask PII from a chat message.
    Removes email/phone and replaces titled names / interviewer hints.
    """
    if not text:
        return text

    original_len = len(text)

    text = _EMAIL.sub("[EMAIL REDACTED]", text)
    text = _PHONE.sub("[PHONE REDACTED]", text)
    text = _TITLED_NAME.sub("[NAME REDACTED]", text)
    text = _INTERVIEWER_HINT.sub(
        lambda m: f"{m.group(1)} [NAME REDACTED]", text
    )

    if len(text) != original_len:
        log.debug(
            "PII: masked chat message | original_len=%d → masked_len=%d",
            original_len, len(text),
        )

    return text
