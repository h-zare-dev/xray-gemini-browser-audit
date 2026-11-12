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

A large **red instruction panel** appears when Chrome opens:

1. Sign in to Google in that Chrome window.
2. Send a test message and confirm Gemini replied.
3. **Leave Chrome open**.
4. Return to the terminal and press **Enter**.

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

### Configure retries and response timeout in `.env`

Add these values to your **local** `.env` file (or copy them from
`.env.example`):

```dotenv
RETRIES=3
ANSWER_WAIT=70
```

`RETRIES` is the maximum number of attempts for errors/uncertain
results (minimum 3). A confirmed `WEB_OK` stops after one attempt.
`ANSWER_WAIT` is the number of seconds to wait for Gemini's reply
**after sending a prompt**; it is not the page navigation timeout.

**Precedence:** explicit command-line option > local `.env` > built-in
default. For example, `python src/session_audit.py --answer-wait 100
--retries 4` overrides the .env for that run only.

### Terminal colors, pacing and retries

The current auditor uses clear colored status lines:

- **GREEN / OK**: Generated marker found inside Gemini's response element (`WEB_OK`).
- **YELLOW / CHECK**: Login challenge, possible reply, missing editor or inconsistent outcomes. **Do not remove this server from the balancer.**
- **RED / BLOCKED**: A country restriction explicitly appeared on **all three attempts**. A repeated network failure is also marked red, but still needs review before permanent removal.

Default behavior: `--ready-wait 25` seconds for page/editor readiness,
`--timeout 55` seconds for navigation, `--answer-wait 70` seconds for a
generated answer, `--retries 3`, `--retry-delay 7` seconds, and
`--pause 8` seconds between ports. Any uncertain/error result is retried
three times; successful `WEB_OK` stops early. Screenshots are saved per
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
