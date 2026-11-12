"""Load VLESS sources from local .env or a remote subscription; parse flexible ports.

Only explicit HTTP(S) subscription URLs are fetched; never log secrets.
"""
import base64
import ipaddress
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MAX_SUBSCRIPTION_BYTES = 4_000_000
MAX_TARGETS = 1000


@dataclass(frozen=True)
class Target:
    name: str
    uri: str
    port: int


def read_env(path: str) -> dict:
    env = {}
    file = Path(path)
    if not file.exists():
        return env
    for line in file.read_text(encoding="utf8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        env[key.strip()] = value
    return env


def ports_from_spec(spec: str) -> list[int]:
    if not spec or not spec.strip():
        raise ValueError("PORTS cannot be empty in VLESS mode")
    ports = []
    for part in spec.split(","):
        part = part.strip()
        match = re.fullmatch(r"(\d{1,5})(?:\s*-\s*(\d{1,5}))?", part)
        if not match:
            raise ValueError(f"Invalid port expression: {part!r}")
        lo = int(match.group(1))
        hi = int(match.group(2) or lo)
        if not 1 <= lo <= hi <= 65535:
            raise ValueError(f"Invalid/reversed port range: {part}")
        if hi - lo > 1000:
            raise ValueError("A single port range must not exceed 1001 entries")
        ports.extend(range(lo, hi + 1))
        if len(ports) > MAX_TARGETS:
            raise ValueError(f"Too many ports; maximum {MAX_TARGETS}")
    return list(dict.fromkeys(ports))


def decode_base64(value: str) -> str:
    raw = re.sub(r"\s+", "", value.strip())
    raw = raw.replace("-", "+").replace("_", "/")
    padded = raw + "=" * (-len(raw) % 4)
    return base64.b64decode(padded, validate=True).decode("utf8")


def subscription_links(text: str) -> list[str]:
    """Standard plain links or base64-encoded list. Clash YAML is not supported."""
    text = text.lstrip("\ufeff").strip()
    if not text:
        raise ValueError("Empty subscription")
    if "://" not in text:
        try:
            text = decode_base64(text)
        except Exception as exc:
            raise ValueError("Subscription is not plaintext URI lines or base64 URI lines") from exc
    links = []
    for line in text.splitlines():
        line = line.strip().strip("\ufeff")
        if not line or line.startswith("#"):
            continue
        if re.match(r"(?i)^[a-z][a-z0-9+.-]*://", line):
            links.append(line)
    if not links:
        raise ValueError("No proxy URI entries found. Clash YAML/JSON subscriptions aren't supported yet.")
    return links


def fetch_subscription(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("SUBSCRIPTION_URL must be HTTP(S)")
    if parsed.username or parsed.password:
        raise ValueError("Credentials in subscription URL are not supported")
    host = parsed.hostname
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise ValueError("Subscription URL points to a non-public IP")
    except ValueError as exc:
        if "non-public" in str(exc):
            raise
    req = Request(url, headers={"User-Agent": "XrayGeminiAudit/0.2", "Accept": "text/plain"})
    with urlopen(req, timeout=20) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_SUBSCRIPTION_BYTES:
            raise ValueError("Subscription is too large")
        content = response.read(MAX_SUBSCRIPTION_BYTES + 1)
        if len(content) > MAX_SUBSCRIPTION_BYTES:
            raise ValueError("Subscription exceeds size limit")
        return content.decode("utf8-sig")


def targets_from_env(env: dict, ports_override: str | None = None):
    """Return (targets, skipped) without printing credential-bearing URLs."""
    mode = env.get("MODE", "vless").strip().lower()
    if mode == "vless":
        uri = env.get("VLESS_URL", "").strip()
        if not uri.lower().startswith("vless://"):
            raise ValueError("VLESS_URL must start with vless://")
        ports = ports_from_spec(ports_override if ports_override is not None else env.get("PORTS", ""))
        return [Target(f"VLESS_{port}", uri, port) for port in ports], []
    if mode != "subscription":
        raise ValueError("MODE must be vless or subscription")
    url = env.get("SUBSCRIPTION_URL", "").strip()
    if not url:
        raise ValueError("SUBSCRIPTION_URL is required")
    entries = subscription_links(fetch_subscription(url))
    targets, skipped = [], []
    for idx, uri in enumerate(entries, 1):
        parsed = urlparse(uri)
        if parsed.scheme.lower() != "vless":
            skipped.append((idx, parsed.scheme.lower() or "unknown", "Unsupported protocol (currently VLESS TCP/RAW only)"))
            continue
        if not parsed.hostname or not parsed.port:
            skipped.append((idx, "vless", "Invalid destination/port"))
            continue
        from vless import outbound_from_url
        try:
            outbound_from_url(uri)
        except (ValueError, TypeError) as exc:
            skipped.append((idx, "vless", f"Unsupported/invalid VLESS settings: {str(exc)[:100]}"))
            continue
        name = (parsed.fragment or f"Node_{idx}")
        from urllib.parse import unquote
        targets.append(Target(unquote(name)[:100], uri, parsed.port))
        if len(targets) > MAX_TARGETS:
            raise ValueError(f"Subscription has over {MAX_TARGETS} supported nodes")
    return targets, skipped
