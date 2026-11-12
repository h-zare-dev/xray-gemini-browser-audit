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

## Log in once (visible browser)

```bash
python src/audit.py --login --login-port 23007
```

Paste a working VLESS URL **when prompted**, then manually sign into Gemini in the Chromium window. Cookies are stored only in `.local/browser-profile/` (ignored by Git). Use a separate test account if possible; Google may request reauthentication after IP switches.

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
