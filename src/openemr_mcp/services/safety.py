"""Drug name and input sanitization for openemr-mcp."""

import unicodedata


def sanitize_drug_name(drug_name: str) -> str:
    """
    Sanitize a drug name field before using it in an external API call or DB write.
    Raises ValueError if the input is clearly malicious.
    """
    if not drug_name:
        return drug_name
    cleaned = drug_name.strip()
    if len(cleaned) > 200:
        raise ValueError(f"Drug name too long ({len(cleaned)} chars); max 200.")
    cleaned = "".join(c for c in cleaned if unicodedata.category(c)[0] != "C" or c in ("\t", "\n"))
    lower = cleaned.lower()
    _injection_patterns = [
        "ignore",
        "disregard",
        "forget your",
        "override",
        "jailbreak",
        "dan mode",
        "act as",
        "you are now",
        "developer mode",
        "no restriction",
        "system prompt",
        "repeat the text above",
        "ignorez",
        "<|im_start|>",
        "<|im_end|>",
        "<|system|>",
        "```system",
        "```python",
        "```bash",
    ]
    for pattern in _injection_patterns:
        if pattern in lower:
            raise ValueError(f"Drug name contains disallowed content: {pattern!r}")
    _sql_patterns = ["'; drop", "'; select", "1=1", "or 1=1", "union select", "--"]
    for pattern in _sql_patterns:
        if pattern in lower:
            raise ValueError(f"Drug name contains SQL injection pattern: {pattern!r}")
    _html_patterns = ["<script", "javascript:", "onerror=", "onload=", "<iframe", "data:text"]
    for pattern in _html_patterns:
        if pattern in lower:
            raise ValueError(f"Drug name contains HTML injection pattern: {pattern!r}")
    if "\n" in cleaned or ";" in cleaned:
        raise ValueError("Drug name contains disallowed delimiter characters.")
    return cleaned


def is_safe_drug_name(drug_name: str) -> bool:
    try:
        sanitize_drug_name(drug_name)
        return True
    except ValueError:
        return False
