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
