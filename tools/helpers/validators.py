import re

TC_BANDWIDTH_RE: re.Pattern[str] = re.compile(r"[0-9]+[KMGT]bit", re.IGNORECASE)

def validate_bandwidth(value: str) -> str | None:
    bandwidth = value.strip()
    if not bandwidth:
        return None
    if bandwidth.lower() == "inf":
        return None
    return None if TC_BANDWIDTH_RE.fullmatch(bandwidth) else "Use e.g. 10kbit, 1mbit or inf"
