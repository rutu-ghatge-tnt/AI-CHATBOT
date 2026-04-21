"""Port of src/utils/escapeRegex.js — escape special regex characters in user input."""


def escape_regex(value: str) -> str:
    return "".join("\\" + c if c in r"\^$*+?.()|[]{}]" else c for c in value)
