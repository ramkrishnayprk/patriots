import re
from dataclasses import dataclass
from typing import Any

REFERENCE_PATTERN = re.compile(
    r"\b(?:it|this\s+(?:movie|film)|that\s+(?:movie|film)|"
    r"the\s+(?:movie|film))\b",
    re.IGNORECASE,
)
BARE_FOLLOWUP_PATTERN = re.compile(
    r"^\s*(?:"
    r"(?:please\s+)?(?:explain|tell\s+me)\s+more"
    r"|more\s+(?:details|information|info)"
    r"|what\s+else"
    r")\s*[?.!]*\s*$",
    re.IGNORECASE,
)
FIELD_FOLLOWUPS = (
    (
        re.compile(
            r"^\s*(?:and\s+)?(?:what\s+about\s+)?(?:its|the)\s+director"
            r"\s*[?.!]*\s*$",
            re.IGNORECASE,
        ),
        "Who directed {title}?",
    ),
    (
        re.compile(
            r"^\s*(?:and\s+)?(?:what\s+about\s+)?(?:its|the)\s+(?:cast|actors?)"
            r"\s*[?.!]*\s*$",
            re.IGNORECASE,
        ),
        "Who is in {title}?",
    ),
    (
        re.compile(
            r"^\s*(?:and\s+)?(?:what\s+about\s+)?(?:its|the)\s+(?:writer|writers)"
            r"\s*[?.!]*\s*$",
            re.IGNORECASE,
        ),
        "Who wrote {title}?",
    ),
    (
        re.compile(
            r"^\s*(?:and\s+)?(?:what\s+about\s+)?(?:its|the)\s+(?:rating|runtime)"
            r"\s*[?.!]*\s*$",
            re.IGNORECASE,
        ),
        "What is the {field} of {title}?",
    ),
)


@dataclass(frozen=True)
class ConversationalRewrite:
    original_query: str
    rewritten_query: str
    referenced_title: str
    strategy: str = "recent_single_source"


def resolve_conversational_reference(
    query: str,
    history: list[dict[str, Any]],
) -> ConversationalRewrite | None:
    """Resolve obvious movie references from the latest unambiguous source."""
    title = _most_recent_single_title(history)
    if not title:
        return None

    stripped = query.strip()
    if BARE_FOLLOWUP_PATTERN.match(stripped):
        return ConversationalRewrite(
            original_query=query,
            rewritten_query=f"Tell me more about {title}",
            referenced_title=title,
        )

    for pattern, template in FIELD_FOLLOWUPS:
        match = pattern.match(stripped)
        if not match:
            continue
        field_match = re.search(r"\b(rating|runtime)\b", stripped, re.IGNORECASE)
        rewritten = template.format(
            title=title,
            field=field_match.group(1).lower() if field_match else "",
        )
        return ConversationalRewrite(
            original_query=query,
            rewritten_query=rewritten,
            referenced_title=title,
        )

    if not REFERENCE_PATTERN.search(stripped):
        return None
    rewritten = REFERENCE_PATTERN.sub(title, stripped)
    return ConversationalRewrite(
        original_query=query,
        rewritten_query=rewritten,
        referenced_title=title,
    )


def _most_recent_single_title(history: list[dict[str, Any]]) -> str | None:
    for message in reversed(history):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        sources = message.get("sources")
        if not isinstance(sources, list):
            continue
        titles = {
            str(source.get("title") or "").strip()
            for source in sources
            if isinstance(source, dict) and str(source.get("title") or "").strip()
        }
        if len(titles) == 1:
            return titles.pop()
        if len(titles) > 1:
            return None
    return None
