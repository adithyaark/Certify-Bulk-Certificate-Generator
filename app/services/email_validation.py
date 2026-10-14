from __future__ import annotations

import re


_MAILBOX_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)


def validate_single_mailbox(value: object, *, field_name: str = "Email") -> str:
    """Return a normalized bare mailbox, rejecting lists and header controls."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a single valid mailbox")

    mailbox = value.strip()
    if (
        not mailbox
        or len(mailbox) > 254
        or any(character.isspace() for character in mailbox)
        or any(ord(character) < 32 or ord(character) == 127 for character in mailbox)
        or "," in mailbox
        or ";" in mailbox
        or not _MAILBOX_PATTERN.fullmatch(mailbox)
    ):
        raise ValueError(f"{field_name} must be a single valid mailbox")
    return mailbox


def contains_header_control(value: object) -> bool:
    """Return whether a value can inject a folded or malformed email header."""
    return isinstance(value, str) and any(
        ord(character) < 32 or ord(character) == 127 for character in value
    )
