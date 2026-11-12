"""Build an Xray VLESS client outbound while preserving encryption parameters."""
import urllib.parse


def outbound_from_url(uri: str) -> dict:
    u = urllib.parse.urlparse(uri.strip())
    if u.scheme != "vless" or not u.username or not u.hostname:
        raise ValueError("Expected vless://UUID@host:port?...")
    qs = {k: values[-1] for k, values in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
    network = qs.get("type", "tcp").lower()
    if network not in ("tcp", "raw"):
        raise ValueError("Only VLESS TCP/RAW is supported")
    security = qs.get("security", "none").lower()
    if security not in ("none", "tls", "reality"):
        raise ValueError(f"Unsupported security: {security}")
    user = {"id": urllib.parse.unquote(u.username), "encryption": qs.get("encryption", "none")}
    if qs.get("flow"):
        user["flow"] = qs["flow"]
    stream = {"network": "tcp" if network == "tcp" else "raw", "security": security}
    if security == "tls":
        stream["tlsSettings"] = {"serverName": qs.get("sni", u.hostname)}
    elif security == "reality":
        if not qs.get("pbk") or not qs.get("sni"):
            raise ValueError("REALITY requires pbk and sni")
        stream["realitySettings"] = {
            "serverName": qs["sni"], "fingerprint": qs.get("fp", "chrome"),
            "password": qs["pbk"], "shortId": qs.get("sid", ""), "spiderX": qs.get("spx", "/")
        }
    return {
        "tag": "PROXY", "protocol": "vless",
        "settings": {"vnext": [{"address": u.hostname, "port": u.port or 443, "users": [user]}]},
        "streamSettings": stream
    }


def xray_config(outbound: dict, port: int, socks_port: int) -> dict:
    import copy
    ob = copy.deepcopy(outbound)
    ob["settings"]["vnext"][0]["port"] = port
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [{"listen": "0.0.0.0", "port": socks_port,
                      "protocol": "socks", "settings": {"auth": "noauth", "udp": False},
                      "tag": "LOCAL_SOCKS"}],
        "outbounds": [ob, {"tag": "BLOCK", "protocol": "blackhole"}],
        "routing": {"rules": [{"type": "field", "inboundTag": ["LOCAL_SOCKS"], "outboundTag": "PROXY"}]}
    }
