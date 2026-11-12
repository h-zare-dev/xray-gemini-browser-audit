# Changelog

All notable changes to this project will be documented here.

## [1.0.0] - 2026-11-12

First documented public release baseline.

### Features
- Browser-based Gemini Web checks using official Google Chrome and Playwright CDP.
- VLESS over TCP/RAW with none, TLS, or REALITY transport security via Dockerized Xray Core.
- Single VLESS URL tested across comma-separated ports and inclusive port ranges.
- Plaintext or base64 line-list subscription import; each supported VLESS node tested at its original host and port.
- Local .env configuration with CLI overrides and no secret values in repository templates.
- Optional direct Google sign-in phase before launching the proxied test Chrome.
- Fast pre-submit editor/region checks; separate response wait and stable assistant-response detection.
- Configurable retries, timeouts, pauses, Docker image, browser profile and report directory.
- Color-coded OK / CHECK / BLOCKED terminal output and CSV attempt details.
- Per-run timestamped report directories and local screenshots, including partial reports on interruption.
- Automatic cleanup of the dedicated Chrome test process by default.

### Known limitations
- A Gemini Web result is not proof of Gemini Android compatibility.
- Browser state, connection reuse, region controls and login challenges may affect results.
- Subscription support is restricted to plaintext/base64 URI lists of supported VLESS TCP/RAW links. Clash YAML/JSON, VMess, Trojan, Shadowsocks and WS/gRPC/XHTTP are not supported.
- Region-block detection is based on explicit page text; absence of an editor alone is inconclusive.
- No production balancer changes, routing exclusions or server configuration changes.

### Verification
- The project has source-level unit tests and GitHub Actions configuration.
- Live end-to-end behavior depends on the user's Chrome, Google account, proxy destinations and network. A formal comprehensive release qualification has not been claimed.
