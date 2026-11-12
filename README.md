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

## Recommended: single native Chrome window (experimental)

This mode keeps **one standard Google Chrome window** open while testing three ports. It uses CDP to inspect the page but does not launch a new Playwright-controlled Chrome for every port. You sign in manually inside this window before the tests start. Xray itself still runs in temporary Docker containers.

```bash
git pull origin main
python src/session_audit.py --ports 23001,23004,23007
```

Paste the VLESS URL when prompted (hidden). Chrome opens through the first port, then sign in manually and **verify Gemini can actually answer**. Leave Chrome open and press Enter in the terminal to start testing all selected ports.

Do not run `--login` or another Chrome process using this same dedicated profile at the same time. Google may still challenge the login after the exit IP changes. This tool labels guest mode as `LOGIN_REQUIRED` and ambiguous responses as `INCONCLUSIVE`, never "Gemini working".

*Known limitation:* Chrome connections/DNS/session state can persist across port switches. Treat results as preliminary until verified by fresh requests and screenshots. Chrome's security systems may block automation or reauthentication; we do not bypass them.

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
