# Xray Gemini Browser Audit

Prototype Python tool to test Gemini **Web** through 61 dedicated Xray VLESS/WireGuard test ports using **official Xray Core Docker** and Playwright Chromium.

**Important:** A successful Gemini API request does not prove that Gemini Web or Android works. A browser response is also not proof that Android supports the same IP. This tool never changes PasarGuard or balancer selectors.

## Install (Linux)

Requires Python 3.10+, Docker, and Chromium installed via Playwright.

```bash
git clone https://github.com/h-zare-dev/xray-gemini-browser-audit.git
cd xray-gemini-browser-audit
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
docker pull ghcr.io/xtls/xray-core:26.3.27
```

## Log in using ordinary Chrome (not Playwright)

Google may refuse sign-in inside an automated browser with the message **"This browser or app may not be secure"**. Google explicitly lists automation-controlled browsers as a possible cause. This is not a WireGuard failure.

Install the official Google Chrome browser on the Linux laptop. Then run:

```bash
python src/audit.py --login
# Equivalent: python src/login.py
```

This opens **normal Chrome, without Playwright, without proxy, and without Docker**, with a fresh local profile at `.local/browser-profile`. Sign into `https://gemini.google.com/app` manually, then close this Chrome window completely.

Next, run the test using the same local profile and official Chrome executable:

```bash
python src/audit.py --ports 23001,23004,23007 --headed
```

The audit asks for your VLESS URI through hidden input, then runs official Xray inside Docker to proxy only the test Chrome. A country/account recheck may happen when the public IP changes; **Google may still deny automated sessions or request reauthentication**. We will not disable security safeguards or guarantee sign-in.

Do not run normal Chrome and audit simultaneously with the same dedicated profile. Never publish, upload, or copy the profile. Google session cookies can grant account access.

## Run with `.env` (recommended)

The project supports two modes and does not need a CSV input. Sensitive input
stays on your laptop in `.env`, excluded from Git by `.gitignore`.

```bash
git pull origin main
cp .env.example .env
chmod 600 .env
nano .env
```

**Single VLESS URL, many ports** (example):

```dotenv
MODE=vless
VLESS_URL=vless://YOUR-OWN-CONNECTION-URL
PORTS=21001-21009,22001-22010,23001-23008,24001-24009,25001-25025
```

Run:

```bash
python src/session_audit.py
```

Or override the ports for a quick test:

```bash
python src/session_audit.py --ports 23001,23004,23007
python src/session_audit.py --ports 21001-21009,23001-23008,25001-25025
```

Both comma-separated ports and inclusive hyphen ranges work. Only specified
ports will be tested. There is no need for `data/ports.csv`.

**Subscription URL, each entry's own host and port**:

```dotenv
MODE=subscription
SUBSCRIPTION_URL=https://your-provider.example/subscription/TOKEN
```

Then:

```bash
python src/session_audit.py
```

Supported: plaintext VLESS links (one per line) or a base64-encoded plaintext
list. Unsupported protocols (VMess, Trojan, Shadowsocks), Clash YAML/JSON, and
VLESS transports beyond TCP/RAW are **not tested**; skipped formats appear in
the terminal. For subscription mode, the program tests each link's original
server and port, **not** the `PORTS` ranges.

### Login first without Xray (default)

The login phase must **not** use the tested VLESS/WireGuard exit IP.
With `LOGIN_DIRECT=true` in your **local** `.env`:

1. Ordinary Chrome opens with `--no-proxy-server`, on the laptop's own internet connection, with the dedicated local profile.
2. Sign into Google manually and press Enter in the terminal.
3. The script closes that direct-login Chrome, waits for the profile to be released, then starts a *new* Chrome **via Xray SOCKS** using the same local profile.
4. The tests begin automatically. Login credentials are never sent to GitHub or stored in `.env`.

**Direct login does not guarantee Google retains the session** after
switching to a different exit country; Google can ask for login or identity
verification again. Those cases should be treated as `LOGIN_REQUIRED`
rather than evidence the target server is broken.

To skip the direct-login step if already authenticated, set
`LOGIN_DIRECT=false` or pass `--skip-direct-login`. For a fresh login
run, leave `LOGIN_DIRECT=true` or pass `--login-direct`.
The direct-login Chrome is always closed before tests, regardless of
`CLOSE_BROWSER`. The test Chrome is closed after tests when
`CLOSE_BROWSER=true`.

### Two distinct time budgets

The script treats the Gemini test as two separate phases:

- **Before sending**: `READY_WAIT=15` seconds is the *combined* maximum for loading the page and finding its prompt textbox. A clear country-block message is recognized immediately. Without a textbox after 15 seconds, no prompt is sent, and the outcome is `NO_EDITOR` (yellow).
- **After sending**: `ANSWER_WAIT=70` seconds starts **only after** successfully submitting the prompt. Gemini Pro may need 30+ seconds; increase this independently as needed.

`TIMEOUT` is the upper limit for page navigation, but in the first phase
navigation is also capped by remaining `READY_WAIT`; setting `TIMEOUT=50`
does **not** make a missing textbox wait 50 seconds.

A blocked country landing page is explicit evidence of a Gemini **Web**
restriction; a missing textbox alone is *not* sufficient evidence of a
country block. Retries remain configurable.

### Response detection behavior

The auditor now waits for a stable **assistant response** inside the `model-response`
element. A duplicate test marker elsewhere on the page no longer ends the
attempt immediately. The assistant reply must stay unchanged for at least
`--response-stable 4` seconds before `WEB_OK` can be reported. If the
response container is missing, the audit waits through `--answer-wait`
before returning `RESPONSE_CANDIDATE` or `INCONCLUSIVE`.

For a slower three-port check:

```bash
python src/session_audit.py --ports 23001,23004,23007 \\
  --answer-wait 100 --response-stable 5 --ready-wait 35 --retries 3
```

The browser layout is not a stable public API; if Google changes its DOM
the script can still report yellow for a valid answer. Verify corresponding
screenshots instead of treating that as a failed proxy.

### Full `.env` configuration

The settings in `.env.example` are the recommended defaults. Copy only
once if you do not already have a private `.env`, then add your own
`VLESS_URL` or `SUBSCRIPTION_URL`.

```bash
git pull origin main
# Only if .env does not already exist:
cp -n .env.example .env
chmod 600 .env
nano .env
python src/session_audit.py
```

| Env key | Default | Meaning |
| --- | --- | --- |
| `MODE` | `vless` | `vless` or `subscription` |
| `VLESS_URL` | blank | Private single VLESS URL |
| `PORTS` | 61 test ports | Comma-separated ports and inclusive ranges |
| `SUBSCRIPTION_URL` | blank | Private subscription address |
| `RETRIES` | `3` | Attempts for uncertain/error results (minimum 1) |
| `ANSWER_WAIT` | `70` | Seconds waiting for Gemini reply after submitting |
| `TIMEOUT` | `55` | Page navigation timeout in seconds |
| `READY_WAIT` | `15` | Total time budget for navigation + finding the prompt editor |
| `RESPONSE_STABLE` | `4` | Seconds model response stays stable before marking OK |
| `RETRY_DELAY` | `7` | Seconds between retry attempts |
| `PAUSE` | `8` | Seconds between ports |
| `LOGIN_DIRECT` | `true` | Open normal Chrome without Xray for manual Google sign-in first |
| `CLOSE_BROWSER` | `true` | Close dedicated test Chrome after completion or Ctrl+C |
| `CHROME_PATH` | empty | Optional Google Chrome executable override |
| `PROFILE_DIR` | `.local/browser-profile` | Local Chrome user profile |
| `OUTPUT_DIR` | `reports/session` | CSV and screenshots |
| `SOCKS_PORT` | `18998` | Local SOCKS port |
| `XRAY_IMAGE` | `ghcr.io/xtls/xray-core:26.3.27` | Official Docker image |
| `XRAY_STARTUP_TIMEOUT` | `20` | Seconds to wait for local Xray startup |

The terminal still accepts optional overrides, e.g. `--retries 4`,
`--answer-wait 100`, `--timeout 70`, and `--keep-browser`.
Precedence: command line > `.env` > built-in defaults.

The audit only closes its **dedicated** Chrome process. It never touches the
ordinary Chrome profile. Existing Chrome login/session data persists under
`.local/browser-profile` unless you delete it. Neither profile nor `.env`
is committed to Git.

### Terminal colors, pacing and retries

The current auditor uses clear colored status lines:

- **GREEN / OK**: Generated marker found inside Gemini's response element (`WEB_OK`).
- **YELLOW / CHECK**: Login challenge, possible reply, missing editor or inconsistent outcomes. **Do not remove this server from the balancer.**
- **RED / BLOCKED**: A country restriction explicitly appeared on **all three attempts**. A repeated network failure is also marked red, but still needs review before permanent removal.

Default behavior: `--ready-wait 15` seconds **total for page navigation and editor readiness**,
`--timeout 55` seconds for navigation, `--answer-wait 70` seconds for a
generated answer, `--retries 3`, `--retry-delay 7` seconds, and
`--pause 8` seconds between ports. Any uncertain/error result is retried
up to the configured number of times; successful `WEB_OK` stops early. Screenshots are saved per
attempt as `PORT_tryN.png`. More deliberate testing:

```bash
python src/session_audit.py --ports 23001,23004,23007 --retries 3 --ready-wait 35 --answer-wait 90 --retry-delay 10 --pause 10
```

The output CSV includes `attempts` and `attempt_results`. A colored line
or green result only describes **Gemini Web**, never guarantees Gemini Android
works with that exit IP. Browser transport may reuse state across proxies;
do not treat one run as proof for changing production balancers.

After that, the report is `reports/session/results.csv`. Screenshots are also
stored locally. The browser is launched through Xray Docker, but there is no
Xray installation on the host.

**Known limitation:** An authenticated session may not persist when Google
requires verification after IP changes. Reusing Chrome while restarting Xray
may also retain existing network connections. Treat `RESPONSE_CANDIDATE`
as **unverified**, not a guarantee of successful Gemini use on Android.
Do not remove balancer members on this evidence alone.

## Compare with known Android results

```bash
python src/audit.py --ports 23001,23004,23007 --headed
```

Observed on Android: 23001 and 23004 show unsupported-country errors; 23007 generates a response. The browser may behave differently. The detection is experimental and screenshots require review.

## All 61

```bash
python src/audit.py
```

Results are written to `reports/results.csv` with screenshots under `reports/`. The program reports `REGION_BLOCKED`, `WEB_RESPONSE_DETECTED`, `LOGIN_OR_CHALLENGE`, `INCONCLUSIVE`, or `TEST_ERROR`. It does not automatically exclude any server.

## Security

Never commit VLESS links, UUIDs, API keys, passwords, Google cookies, browser profiles or personal screenshots. Browser profile and results are ignored by Git. Xray runs as an ephemeral Docker container; it is not installed on the host.

**Prototype limitations:** the web page layout changes, login challenges, and changing account security state can all affect detection. Test results are not sufficient alone for production balancer removals.
