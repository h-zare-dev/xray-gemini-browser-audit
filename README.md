# Xray Gemini Browser Audit

[راهنمای فارسی | Persian setup and usage guide](docs/README.fa.md)

![Version](https://img.shields.io/badge/version-v1.0.0-blue)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Xray-Docker-2496ED?logo=docker&logoColor=white)
![Status](https://img.shields.io/badge/status-browser--audit-orange)

**Test Gemini Web access through VLESS/Xray exit routes, compare multiple ports or subscription nodes, and save reproducible local reports.**

Xray Gemini Browser Audit is a Python command-line utility for Linux. It runs the official Xray Core container as a local SOCKS5 gateway, controls a dedicated **Google Chrome** test profile through Playwright's Chrome DevTools Protocol (CDP), sends a distinctive test prompt to Gemini Web, and classifies the browser-visible outcome.

> **Scope:** This tests **Gemini Web**, not Gemini Android. A browser `OK` does not prove that Android will work with the same exit IP. This project does not modify Xray servers, PasarGuard settings, WireGuard peers or production balancers.

**Release baseline:** `v1.0.0` — see [CHANGELOG.md](CHANGELOG.md) and [VERSION](VERSION). This is the initial documented version, **not a claim of exhaustive end-to-end certification**.

## Features

- **VLESS port mode:** take one private VLESS URL and check individual ports or inclusive ranges such as `21001-21009,23001,23004,25001-25025`.
- **Subscription mode:** download a plaintext or base64-encoded list of proxy URIs and test every *supported* VLESS entry using its own host and port.
- **Two-step login:** optionally sign in with ordinary Google Chrome using a **direct, unproxied connection**, then reopen the same local profile through Xray to conduct checks.
- **Two separate time budgets:** fast country-block/editor checks *before* submitting; longer model-response wait *after* submitting.
- **Evidence-based results:** detect explicit country restrictions, verified model responses, transient failures, login challenges and ambiguous states.
- **Retries and readable logs:** configurable retry count and delays, plus green/yellow/red terminal messages.
- **Isolated reports:** a new timestamped directory for each run, with CSV and per-attempt screenshots.
- **Secret hygiene:** credentials stay in your local `.env` and Chrome profile, both ignored by Git.
- **Ephemeral Xray:** use a Docker image; no Xray installation required on the Linux host.

## Requirements

- Linux computer with **Python 3.10+**
- Docker daemon working for your user (`docker info` should succeed)
- Official **Google Chrome** installed (`google-chrome-stable` or `google-chrome`)
- Internet access to Google and a working VLESS server
- A compatible VLESS URL or subscription
- Desktop session for the initial manual Chrome sign-in

The code is not a headless Google login bypass. Google may demand verification or refuse a session after the public IP changes. Chrome is separate from your everyday browsing profile.

## Quick start

```bash
git clone https://github.com/h-zare-dev/xray-gemini-browser-audit.git
cd xray-gemini-browser-audit

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Verify installed dependencies
google-chrome-stable --version  # or: google-chrome --version
docker info
docker pull ghcr.io/xtls/xray-core:26.3.27

# Initialize private settings once
cp .env.example .env
chmod 600 .env
nano .env
```

**Never overwrite your existing private `.env` when upgrading.** If your `.env` already exists, edit it rather than copying the example again. The script uses installed Google Chrome; `python -m playwright install chromium` is **not necessary** for the recommended `session_audit.py` workflow.

### Mode A: one VLESS URL across ports

Edit `.env`:

```dotenv
MODE=vless
VLESS_URL=vless://YOUR-OWN-PRIVATE-URL
PORTS=21001-21009,22001-22010,23001-23008,24001-24009,25001-25025
```

Run all ports configured in `.env`:

```bash
python src/session_audit.py
```

Or select only a few for a quick comparison:

```bash
python src/session_audit.py --ports 23001,23004,23007
python src/session_audit.py --ports 21001-21009,24001,25001-25005
```

The original connection host, UUID and encryption options are preserved; the **destination port** is varied. Ports are inclusive, comma-separated and deduplicated.

### Mode B: subscription URL

Edit `.env`:

```dotenv
MODE=subscription
SUBSCRIPTION_URL=https://provider.example/your-private-subscription-token
```

Then:

```bash
python src/session_audit.py
```

The subscription must supply **one proxy URI per line**, either as plaintext or as a base64-encoded text list. The script tests each supported VLESS entry's **original host and port**; `PORTS` and `--ports` do not select individual entries in subscription mode.

**Supported:** VLESS `tcp` / `raw` transports with `security=none`, `tls` or `reality` as represented by the project's parser. **Not supported:** Clash YAML/JSON, VMess, Trojan, Shadowsocks, VLESS WS/gRPC/XHTTP or arbitrary Xray JSON. Unsupported URI protocols and incompatible VLESS entries are reported as skipped rather than incorrectly marked as failed. Plaintext HTTP subscription URLs are technically accepted; **HTTPS is strongly recommended** to protect subscription tokens.

## How a run works

1. **Local login (default):** with `LOGIN_DIRECT=true`, the script opens normal Chrome with `--no-proxy-server` and its own local profile. Sign in to your Google account manually, return to the terminal, and press Enter.
2. **Switch to testing:** the login Chrome is closed. A new Chrome instance reuses that profile and connects through the local Docker Xray SOCKS5 proxy.
3. **Check each destination:** load Gemini Web and look for an explicit country-block message or the message textbox. The **entire pre-submit phase** is limited by `READY_WAIT`.
4. **Send and await:** only if the textbox exists, send a unique marker prompt. Wait independently for Gemini's generated reply, subject to `ANSWER_WAIT` and `RESPONSE_STABLE`.
5. **Retry ambiguous failures:** successful verified model replies and explicit country-block pages stop that port immediately. Other uncertain/failed results can be retried according to `RETRIES`.
6. **Save and close:** screenshots and CSV go into a new run folder. By default, the dedicated test Chrome closes automatically; the local login profile is preserved.

**Note on isolation:** the proxy's Xray container changes between destinations while Chrome stays open. Browser connections, DNS caches, cookies and Google account state may persist across ports; treat results as a **screening aid**, not proof of the exact exit IP used by every request.

## Configuration reference

Create your settings by copying [`.env.example`](.env.example). No secret values are included in that template.

| Variable | Default | Purpose |
| --- | --- | --- |
| `MODE` | `vless` | Choose `vless` or `subscription` |
| `VLESS_URL` | empty | Private VLESS link in port mode |
| `PORTS` | 61 example ports | Single ports and inclusive ranges in port mode |
| `SUBSCRIPTION_URL` | empty | Subscription endpoint in subscription mode |
| `RETRIES` | `3` | Maximum attempts for uncertain outcomes; minimum 1 |
| `READY_WAIT` | `15` | Combined seconds for initial navigation and finding the textbox |
| `ANSWER_WAIT` | `70` | Seconds to wait **after sending** the prompt |
| `TIMEOUT` | `55` | General navigation cap; pre-submit stage is also capped by `READY_WAIT` |
| `RESPONSE_STABLE` | `4` | Seconds a matching assistant response must remain stable |
| `RETRY_DELAY` | `7` | Delay between retries, seconds |
| `PAUSE` | `8` | Delay between target ports, seconds |
| `LOGIN_DIRECT` | `true` | Initial Google login via normal unproxied Chrome |
| `CLOSE_BROWSER` | `true` | Close dedicated test Chrome after completion or interruption |
| `CHROME_PATH` | empty | Optional path to official Chrome; otherwise autodetected |
| `PROFILE_DIR` | `.local/browser-profile` | Local dedicated Google Chrome profile |
| `OUTPUT_DIR` | `reports/session` | Parent directory for timestamped run reports |
| `SOCKS_PORT` | `18998` | Local Xray SOCKS5 listener |
| `XRAY_IMAGE` | `ghcr.io/xtls/xray-core:26.3.27` | Xray Docker image |
| `XRAY_STARTUP_TIMEOUT` | `20` | Xray startup wait, seconds |

**Precedence:** an explicit CLI option overrides `.env`; `.env` overrides the built-in default. For example:

```bash
python src/session_audit.py --ports 23007 --retries 2 --ready-wait 15 --answer-wait 100 --response-stable 5
python src/session_audit.py --skip-direct-login --ports 23007
python src/session_audit.py --keep-browser --ports 23007
python src/session_audit.py --env /path/to/private-config.env --output reports/custom
python src/session_audit.py --help
```

`--skip-direct-login` skips the initial direct sign-in phase; it does not guarantee that Google will accept an existing session.

## Output and status definitions

Every run creates a new directory using the computer's **local start time**. Runs starting in the same second get `_01`, `_02` and so forth, rather than overwriting each other.

```text
reports/session/
├── 2026-11-12_21-30-45/
│   ├── results.csv
│   ├── 0001_23001_try1.png
│   ├── 0001_23001_try2.png
│   └── 0002_23007_try1.png
└── 2026-11-12_22-10-03/
    ├── results.csv
    └── 0001_23007_try1.png
```

The CSV includes `timestamp_utc`, `index`, `name`, `port`, `status`, `detail`, `attempts` and `attempt_results`.

| Terminal | CSV status | Interpretation |
| --- | --- | --- |
| 🟢 `OK` | `WEB_OK` | A matching marker was found in the assistant response and became stable |
| 🔴 `BLOCKED` | `REGION_BLOCKED` | Gemini Web explicitly showed an unsupported-country message; no retry |
| 🔴 `NETWORK ERROR` | `CONNECTION_FAILED_CONFIRMED` | Repeated eligible network failures (requires 3 attempts) |
| 🟡 `CHECK` | `NO_EDITOR` | No prompt textbox appeared before `READY_WAIT` expired |
| 🟡 `CHECK` | `LOGIN_REQUIRED` | Google sign-in or identity challenge |
| 🟡 `CHECK` | `RESPONSE_CANDIDATE` | Marker may have appeared, but model response was not verified |
| 🟡 `CHECK` | `INCONCLUSIVE` | No reliable conclusion or inconsistent attempts |

A red country restriction is evidence for **that Gemini Web page load**, not a permanent assessment of the exit IP or proof of Android behavior. A missing editor **by itself** is never enough to label a country block.

To view the newest run locally:

```bash
ls -lt reports/session/
find reports/session -name results.csv -print
```

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Google displays “This browser or app may not be secure” | Complete sign-in using the **direct Chrome** phase; avoid automated sign-in |
| Gemini says “isn't currently supported in your country” | The test page is region-blocked; the program should print `BLOCKED` immediately |
| `NO_EDITOR` / `CHECK` | Check screenshots, login state, load speed and `READY_WAIT`; do not assume the route is blocked |
| `ERR_NETWORK_CHANGED` | May occur when Xray's backend changes; retry and inspect the screenshot |
| Timeout before the textbox appears | Increase `READY_WAIT` only if page loading is slow; `ANSWER_WAIT` does not apply yet |
| Gemini takes long to reply | Increase `ANSWER_WAIT` for slow models, e.g. 90–120 |
| Chrome refuses to launch or the profile is locked | Close old test Chrome processes using the dedicated `PROFILE_DIR`; do not remove your personal Chrome data |
| Local SOCKS unavailable | Check `docker info`, the Xray image, port `SOCKS_PORT`, and Docker permission |
| Subscription yields zero nodes | Verify that it is a plaintext/base64 URI list and contains supported VLESS TCP/RAW links |

## Testing and contributing

```bash
python3 -m compileall -q src
python3 -m unittest discover -s tests -p 'test_*.py'
```

A GitHub Actions workflow runs those checks on pushes and pull requests. This is a lightweight unit test suite; it is **not** an end-to-end Gemini account and network integration test. The script intentionally does not download or commit Chrome session cookies, saved passwords, VLESS UUIDs, or subscription tokens.

## Security and privacy

- Keep `.env`, `.local/`, `reports/`, keys and screenshots on your own machine. They are ignored by [`.gitignore`](.gitignore).
- **Do not paste private VLESS URLs, UUIDs, subscription tokens, API keys, or Google cookies** into public issues, commits, logs or screenshots.
- The dedicated Chrome profile holds authentication material and should be protected like a password.
- The tool sends test prompts to Gemini under the signed-in Google account. Choose appropriate use limits.
- The subscription fetch is performed by your local script; it is not uploaded to GitHub.
- The program does **not** change your server-side routing, firewall or balancer configuration.

## Limitations and roadmap

This is an independent community tool, not affiliated with Google, Mullvad or Xray. Gemini's DOM, availability rules and authentication flows can change. The current proxy parser does not support all Xray transports or subscription formats. Possible future improvements include verifying the actual public exit IP for every probe, better response-container compatibility, full connection isolation per destination, and optional JSON/HTML report summaries.

See [CHANGELOG.md](CHANGELOG.md) for the version history.
