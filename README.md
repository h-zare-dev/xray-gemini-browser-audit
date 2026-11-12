# Xray Gemini Browser Audit

**Version: 1.0.0** · Python · Google Chrome · Playwright (CDP) · official Xray Core Docker

A locally run CLI tool for **testing Gemini Web access through VLESS/Xray connections**. Audit one VLESS connection over explicit destination-port ranges, or load supported VLESS entries from a subscription URL. Each run produces its own timestamped CSV report and screenshots.

> **Scope:** This tests whether **Gemini Web** can load, accept a prompt and produce a recognizable reply in a Chrome session. It **does not** prove Gemini Android availability, the API's regional availability, or that a given WireGuard exit IP was used. Never automatically remove production balancer members based on this output alone.

## Features

- **Two input modes:** one VLESS URI across comma-separated ports and inclusive port ranges; or individual VLESS URIs from a plaintext / Base64 subscription.
- **Private local configuration:** `.env` contains sensitive URLs; it and the browser profile are Git-ignored.
- **Two-stage browser flow:** manual Google login in **ordinary unproxied Chrome**, then a separate Chrome process with Xray SOCKS for auditing.
- **Faster country-block detection:** explicit regional restriction is marked `BLOCKED` immediately, without waiting for a missing message box or retrying that same attempt.
- **Separate timers:** the pre-submit deadline (`READY_WAIT`) and reply deadline (`ANSWER_WAIT`) apply to different stages.
- **Conservative results:** confirmed model reply = `OK`; unresolved prompts, sign-in challenges and loading failures are distinguished. Retry counts are configurable.
- **Per-run artifacts:** a new date-and-time folder for each invocation, including CSV and screenshots of each attempt.
- **Colored terminal output:** green for verified Web reply, yellow for uncertain outcomes, red for explicit country blocks or consistently failed network attempts.
- **Automatic test Chrome cleanup** when `CLOSE_BROWSER=true`.

## Requirements

- Linux desktop (the interactive browser workflow needs a GUI and a usable Chrome display; a headless remote server is **not** a drop-in replacement).
- Python **3.10+** (Python 3.12 is used by CI).
- **Google Chrome** (official browser executable `google-chrome` or `google-chrome-stable`).
- Docker Engine available to the current user; Docker must be running.
- Internet access to download dependencies and the Xray Core image.
- A working **VLESS TCP/RAW** link or a supported subscription; credentials for a Google account if you want an authenticated Web check.

The tool launches official `ghcr.io/xtls/xray-core:26.3.27` in short-lived Docker containers. It does **not** change an existing PasarGuard or production Xray installation.

### 1. Install

```bash
git clone https://github.com/h-zare-dev/xray-gemini-browser-audit.git
cd xray-gemini-browser-audit
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# Optional: browser binaries used by the older Playwright path;
# session_audit.py uses the installed Google Chrome instead.
python -m playwright install chromium

docker info
docker pull ghcr.io/xtls/xray-core:26.3.27
```

If `docker info` fails, start Docker and ensure the current user can access its socket; follow your distribution's Docker setup guidance. Docker socket access typically grants elevated host privileges.

### 2. Set up private `.env`

```bash
cp -n .env.example .env
chmod 600 .env
nano .env
```

**Do not overwrite an existing `.env` with `.env.example`** — it contains your private configuration. Paste credentials only into the local file, not a GitHub issue or commit.

#### Mode A — one VLESS link over ports

```dotenv
MODE=vless
VLESS_URL=vless://YOUR-OWN-VLESS-URI
PORTS=21001-21009,22001-22010,23001-23008,24001-24009,25001-25025
SUBSCRIPTION_URL=
```

The script preserves the VLESS host, UUID, supported transport/security and encryption parameters, but substitutes each requested **destination port**. You can include individual ports and ranges, e.g. `23001,23004,23007-23008`. Ranges include both endpoints; duplicates are removed.

If the URI has a transport other than TCP/RAW, the current parser will not be able to test it.

#### Mode B — subscription URL

```dotenv
MODE=subscription
VLESS_URL=
SUBSCRIPTION_URL=https://your-provider.example/your-private-subscription
```

The program downloads a plaintext URI list (one link per line) or Base64-encoded URI list and tests supported **VLESS entries at their own host and port**. The `PORTS` value is **ignored** in subscription mode. Entries of other protocols are **reported as skipped**, not silently tested. Clash YAML/JSON and VMess/Trojan/Shadowsocks are not supported; neither are VLESS XHTTP/WebSocket/gRPC transports. For subscriptions that are not in the supported format, convert them to a compatible plaintext link list first.

A subscription may contain a secret token. Keep the URL in local `.env`, never in the repository.

### 3. Run

For everything specified by `.env`:

```bash
python src/session_audit.py
```

For selected VLESS ports **without editing `.env`**:

```bash
python src/session_audit.py --ports 23001,23004,23007
python src/session_audit.py --ports 21001-21009,23001-23008
```

For a different private config file:

```bash
python src/session_audit.py --env .env.local --ports 23007
```

**Note:** `--ports` only has an effect in `MODE=vless`; subscription mode tests each supported link with its own port.

#### How manual login works

1. With `LOGIN_DIRECT=true` (the default), Chrome opens **without the Xray proxy** using a dedicated local profile.
2. Log into Google yourself. Check the signed-in avatar, then press **Enter** in the terminal.
3. The script closes that login Chrome, waits briefly for profile files to be released, and launches **test Chrome through local Xray SOCKS** with the same profile.
4. Tests run automatically. With `CLOSE_BROWSER=true`, the script closes its dedicated test Chrome when finished.

**Google can invalidate or challenge a session after an IP/country change.** Login success on the direct connection does not guarantee it remains authenticated when testing other exits. Do not attempt to bypass Google's security protections.

If you already have a valid local profile and want to skip the direct-login window, set `LOGIN_DIRECT=false` or invoke `--skip-direct-login`. Do not run multiple instances against the same Chrome profile at once.

### 4. Configure all runtime settings

The local `.env` is the default configuration source. Command-line flags override its values for one invocation, and built-in defaults apply when an entry is missing.

| `.env` setting | Default | What it controls |
|---|---|---|
| `MODE` | `vless` | `vless` or `subscription` |
| `VLESS_URL` | empty | Private VLESS URI for port-range testing |
| `PORTS` | configured 61-port sample | Comma-separated ports and inclusive ranges |
| `SUBSCRIPTION_URL` | empty | Private plaintext/Base64 subscription URL |
| `RETRIES` | `3` | Maximum attempts for an uncertain/error outcome (minimum 1) |
| `READY_WAIT` | `15` | Combined **pre-submit** budget to navigate and find an editor, in seconds |
| `ANSWER_WAIT` | `70` | Time to wait for Gemini **after sending** a prompt, in seconds |
| `TIMEOUT` | `55` | Navigation cap in seconds; pre-submit is still capped by `READY_WAIT` |
| `RESPONSE_STABLE` | `4` | Seconds the detected model response must stay stable |
| `RETRY_DELAY` | `7` | Seconds between retries on one target |
| `PAUSE` | `8` | Seconds between different targets |
| `LOGIN_DIRECT` | `true` | Open unproxied Chrome for initial manual login |
| `CLOSE_BROWSER` | `true` | Close the test Chrome after the run |
| `CHROME_PATH` | empty | Optional override for the Google Chrome executable |
| `PROFILE_DIR` | `.local/browser-profile` | Local Chrome profile, contains Google session data |
| `OUTPUT_DIR` | `reports/session` | Parent directory for timestamped results |
| `SOCKS_PORT` | `18998` | Locally bound SOCKS5 listening port |
| `XRAY_IMAGE` | `ghcr.io/xtls/xray-core:26.3.27` | Official Docker image |
| `XRAY_STARTUP_TIMEOUT` | `20` | Seconds to wait for Xray's SOCKS listener |

Example tuning for a slower Gemini Pro reply:

```dotenv
RETRIES=3
READY_WAIT=15
ANSWER_WAIT=90
RESPONSE_STABLE=5
RETRY_DELAY=7
PAUSE=8
LOGIN_DIRECT=true
CLOSE_BROWSER=true
```

Equivalent one-off overrides:

```bash
python src/session_audit.py --ports 23007 --retries 3 --ready-wait 15 --answer-wait 90 --response-stable 5
python src/session_audit.py --ports 23007 --keep-browser
```

### 5. Read results

Each run creates a **unique local-time directory**, keeping historical runs separate:

```text
reports/session/
├── 2026-11-12_21-30-45/
│   ├── results.csv
│   ├── 0001_23001_try1.png
│   └── 0002_23007_try1.png
└── 2026-11-12_22-10-03/
    └── results.csv
```

If two runs start in the same second, the second gets a suffix like `_01`. Interrupted runs also save available completed rows into their own report. The script prints the exact report directory and CSV path.

```bash
ls -lt reports/session/
# Find most recent report directory:
latest=$(find reports/session -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)
cat "$latest/results.csv"
```

CSV columns: `timestamp_utc`, `index`, `name`, `port`, `status`, `detail`, `attempts`, `attempt_results`.

| Terminal | CSV status | Interpretation |
|---|---|---|
| 🟢 `OK` | `WEB_OK` | A stable expected marker was detected inside a Gemini assistant response. **Web-only** success. |
| 🔴 `BLOCKED` | `REGION_BLOCKED` | An explicit unsupported-country message appeared; no extra retry needed for that visit. |
| 🔴 `NETWORK ERROR` | `CONNECTION_FAILED_CONFIRMED` | All 3 attempts were classified as retryable network failures. |
| 🟡 `CHECK` | `LOGIN_REQUIRED` | Google login or verification challenge. |
| 🟡 `CHECK` | `NO_EDITOR` | No usable prompt input within `READY_WAIT`. |
| 🟡 `CHECK` | `RESPONSE_CANDIDATE` | A possible reply appeared but did not meet strict response detection. |
| 🟡 `CHECK` | `INCONCLUSIVE` | Mixed or incomplete evidence; do **not** label the IP definitively blocked. |

`attempt_results` captures each underlying attempt status. A green result stops retries early. An explicit regional restriction also stops retries early; other errors can be retried up to `RETRIES`.

### 6. Troubleshooting

**Chrome reports “This browser or app may not be secure” when signing in.** Use the normal direct-login window, not a Chrome instance launched through Playwright automation. Google may still request further verification.

**The initial login page says the country is unsupported.** Make sure `LOGIN_DIRECT=true`; the initial login Chrome should start with `--no-proxy-server`. Check whether your *ordinary laptop connection* is itself a VPN/proxy.

**`NO_EDITOR` or yellow `CHECK`.** A country-block page, login challenge, slow loading, or a changed Gemini UI may hide the editor. Inspect the matching screenshot; do not assume the port is blocked without explicit evidence.

**`ERR_NETWORK_CHANGED` or navigation timeout.** The browser is switching routes while its connections may persist. Results can be transient. Increase `RETRY_DELAY`, `READY_WAIT`, and/or `RETRIES` or verify the affected target manually.

**Gemini visibly answers but status is not green.** The response selector may have changed, or the detected answer did not stabilize. Inspect screenshots; adjust `ANSWER_WAIT` / `RESPONSE_STABLE`. A yellow status is deliberately conservative.

**Docker/Xray SOCKS is unavailable.** Check `docker info`, the configured `XRAY_IMAGE`, and whether `SOCKS_PORT` is already occupied. The container is ephemeral; check Docker daemon permissions.

**Chrome profile appears locked.** Close any other Chrome window using `PROFILE_DIR`. The dedicated profile is separate from your regular browser profile.

**Want all available CLI options?** `python src/session_audit.py --help`.

### 7. Run automated checks

```bash
python -m compileall -q src
python -m unittest discover -s tests -p 'test_*.py'
```

GitHub Actions runs Python checks on pushes and pull requests. These are **unit/static checks**, not a live 61-server Gemini audit. Live behavior depends on the local environment, Google account and exit IPs.

## Security and privacy

- **Never commit** `.env`, private VLESS URIs / UUIDs, subscription tokens, Google passwords, browser profiles, cookies, or screenshots. `.gitignore` excludes the primary local secret/profile/report locations.
- `.env` should have permissions `600`. Consider rotating credentials already shared publicly.
- Local Chrome profiles contain authenticated session data; protect the machine and profile folder.
- The subscription is fetched from the URL supplied by **you**. Only use subscription providers you trust.
- Docker grants powerful host-level privileges to members with socket access.
- Results are local files and are not submitted to this repository or any telemetry endpoint by the script.

## Known limitations

1. **Gemini Web is not Gemini Android.** A Web result cannot establish Android app usability.
2. **Exit IP is not independently verified per target.** Chrome may reuse connection/DNS state when the Xray backend changes; therefore results are observational, not authoritative evidence of the expected exit IP.
3. **Google's UI is not a stable API.** Country/response selectors may need updates as Gemini changes.
4. **Subscriptions are limited to VLESS TCP/RAW link lists.** Other protocols and structured subscriptions are not supported.
5. **Login challenges and regional detection can vary by account, time and provider.**
6. **This is not a balancer manager.** It never changes PasarGuard, Xray, or backend routing configurations.

## Project layout

```text
src/
  session_audit.py     # Recommended CLI: Chrome login + browser testing
  sources.py           # .env, subscription and port parsing
  vless.py             # VLESS URL and Xray config creation
  audit.py             # Xray Docker helper and older audit command
  login.py             # Standalone direct Chrome login
tests/                 # Unit checks
data/ports.csv         # Legacy 61-port reference; not read by session_audit.py
.env.example           # Public sample settings (never secrets)
VERSION                # Release version
CHANGELOG.md           # Release notes
```

## Versioning

The first documented version is **v1.0.0** (see `VERSION` and `CHANGELOG.md`). A Git tag / GitHub Release should only be published after reviewing the corresponding CI results and verifying the desired commit.

## License

No license grant is implied solely by making a repository public. If you want others to reuse, modify or distribute the code under explicit terms, add a suitable `LICENSE` file.
