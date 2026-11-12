#!/usr/bin/env python3
"""Gemini Web audit with .env VLESS/subscription sources and native Chrome.

Experimental web audit only. Does not prove Gemini Android usability.
Never uploads credentials or changes balancer configuration.
"""
import argparse
import csv
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time

from audit import Xray, IMAGE
from sources import read_env, targets_from_env
from vless import outbound_from_url

RED = "\033[1;31m"
YELLOW = "\033[1;33m"
GREEN = "\033[1;32m"
CYAN = "\033[1;36m"
RESET = "\033[0m"
REGION = re.compile(
    r"gemini\s+isn.t\s+(?:currently\s+)?supported\s+in\s+your\s+country"
    r"|(?:this|your)\s+country\s+isn.t\s+supported"
    r"|not\s+available\s+in\s+your\s+(?:country|region)"
    r"|isn.t\s+available\s+in\s+your\s+(?:country|region)"
    r"|not\s+supported\s+in\s+your\s+(?:country|region)",
    re.I,
)
LOGIN = re.compile(r"sign in to save activity|sign in to connect to google apps|couldn.t sign you in|verify it.s you", re.I)


def banner(title, lines, color=RED):
    # Color for interactive terminals, plain text in redirected logs.
    head = color if sys.stdout.isatty() and not os.environ.get("NO_COLOR") else ""
    tail = RESET if head else ""
    width = 76
    print("\n" + head + "╔" + "═" * width + "╗")
    print("║" + title.center(width) + "║")
    print("╠" + "═" * width + "╣")
    for line in lines:
        print("║ " + line.ljust(width - 1)[:width - 1] + "║")
    print("╚" + "═" * width + "╝" + tail, flush=True)


def chrome_bin():
    return shutil.which("google-chrome-stable") or shutil.which("google-chrome")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_cdp(process, port, timeout=25):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if process.poll() is not None:
            return False
        try:
            with socket.create_connection(("127.0.0.1", port), 0.3):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def check_gemini(page, args, label):
    """Probe Gemini Web; a visible prompt alone is never success."""
    # Phase A: total pre-submit budget (navigation + editor readiness).
    # Even if TIMEOUT is large, this stage never intentionally waits longer
    # than READY_WAIT. Phase B uses ANSWER_WAIT only after prompt submission.
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    phase_start = time.monotonic()
    deadline = phase_start + args.ready_wait
    selectors = '[contenteditable="true"]:visible, textarea:visible, [role="textbox"]:visible'
    editors = page.locator(selectors)
    navigation_error = None
    try:
        navigation_budget = max(1000, int(min(args.timeout, args.ready_wait) * 1000))
        page.goto("https://gemini.google.com/app", wait_until="domcontentloaded",
                  timeout=navigation_budget)
    except PlaywrightTimeoutError:
        navigation_error = "Page load exceeded pre-submit budget"
    except Exception as exc:
        if "ERR_NETWORK_CHANGED" in str(exc) or "ERR_CONNECTION" in str(exc):
            navigation_error = "Connection interrupted while loading page"
        else:
            raise

    while time.monotonic() < deadline:
        try:
            # First check country restriction: Gemini can render a blocked
            # landing page without ever creating its prompt editor.
            body = page.locator("body").inner_text(timeout=1000)
            if REGION.search(body):
                return "REGION_BLOCKED", "Gemini says this country is unsupported"
            if LOGIN.search(body) or page.get_by_text("Sign in", exact=True).count() > 0:
                return "LOGIN_REQUIRED", "Google login/verification required"
            if editors.count() > 0:
                break
        except Exception:
            pass
        remaining = deadline - time.monotonic()
        if remaining > 0:
            page.wait_for_timeout(min(700, max(1, int(remaining * 1000))))
    else:
        # No editor within the initial budget. Do not spend ANSWER_WAIT here.
        if navigation_error:
            return "RETRYABLE_NETWORK", navigation_error
        return "NO_EDITOR", "No Gemini message box within ready-wait; no prompt sent"

    marker = f"GEMTEST{label}X".replace("-", "").replace("_", "")
    editor = editors.last
    try:
        editor.fill(f"Reply with exactly {marker}", timeout=12000)
        editor.press("Enter", timeout=12000)
    except Exception:
        return "INCONCLUSIVE", "Could not submit prompt; page may still be loading"
    # A message appearing twice in the *whole body* is not proof of a model
    # answer: the user prompt, drafts and accessibility nodes can duplicate it.
    # We therefore wait for the model-response element AND a stable answer.
    end = time.monotonic() + args.answer_wait
    candidate_seen = False
    last_response = ""
    stable_since = None
    while time.monotonic() < end:
        page.wait_for_timeout(1200)
        try:
            body = page.locator("body").inner_text(timeout=6000)
            if REGION.search(body):
                return "REGION_BLOCKED", "Gemini explicitly rejected country after submission"
            if LOGIN.search(body):
                return "LOGIN_REQUIRED", "Google login or security challenge"

            # Gemini may put Markdown in several nested components; inspect
            # the top-level assistant response, not only .markdown children.
            responses = page.locator("model-response")
            if responses.count():
                response_text = responses.last.inner_text(timeout=5000).strip()
                if marker in response_text:
                    if response_text == last_response:
                        if stable_since is None:
                            stable_since = time.monotonic()
                        elif time.monotonic() - stable_since >= args.response_stable:
                            return "WEB_OK", "Gemini assistant reply detected and stable"
                    else:
                        last_response = response_text
                        stable_since = None
            if body.count(marker) >= 2:
                candidate_seen = True
        except Exception:
            pass
    if candidate_seen:
        return "RESPONSE_CANDIDATE", "Marker appeared but assistant reply not confirmed before timeout"
    return "INCONCLUSIVE", "No confirmed model answer before response timeout"


def state_style(status):
    """Color is based on evidence, not optimistic inference."""
    if status == "WEB_OK":
        return GREEN, "OK"
    if status in ("REGION_BLOCKED", "REGION_BLOCKED_CONFIRMED"):
        return RED, "BLOCKED"
    if status == "CONNECTION_FAILED_CONFIRMED":
        return RED, "NETWORK ERROR"
    return YELLOW, "CHECK"


def consolidate(attempts):
    """Never turn a transient or mixed result into a confirmed failure."""
    states = [row[0] for row in attempts]
    if "REGION_BLOCKED" in states:
        return "REGION_BLOCKED", "Explicit country-block message detected; no retry needed"
    if "WEB_OK" in states:
        return "WEB_OK", "Received a verified model response"
    if len(states) >= 3 and all(st == "REGION_BLOCKED" for st in states):
        return "REGION_BLOCKED_CONFIRMED", "Country restriction repeated on 3 attempts"
    if len(states) >= 3 and all(st == "RETRYABLE_NETWORK" for st in states):
        return "CONNECTION_FAILED_CONFIRMED", "Network failed on all 3 attempts"
    if "LOGIN_REQUIRED" in states:
        return "LOGIN_REQUIRED", "Google login/security challenge: manual review needed"
    if all(st == "NO_EDITOR" for st in states):
        return "NO_EDITOR", "No message box appeared within readiness budget"
    if "RESPONSE_CANDIDATE" in states:
        return "RESPONSE_CANDIDATE", "Possible model response; screenshot review required"
    return "INCONCLUSIVE", "Mixed or inconclusive results; do not remove this server"


def log_result(index, total, target, status, detail, attempts):
    color, label = state_style(status)
    color = color if sys.stdout.isatty() and not os.environ.get("NO_COLOR") else ""
    reset = RESET if color else ""
    print(
        f"{color}[{index:03d}/{total}] {label:<13} "
        f"{target.name[:28]:<28} port={target.port:<5} "
        f"tries={attempts} | {detail}{reset}", flush=True
    )


# Defaults remain unchanged unless overridden explicitly.
DEFAULTS = {
    "PROFILE_DIR": ".local/browser-profile",
    "OUTPUT_DIR": "reports/session",
    "SOCKS_PORT": 18998,
    "TIMEOUT": 55,
    "ANSWER_WAIT": 70,
    "RESPONSE_STABLE": 4,
    "READY_WAIT": 15,
    "RETRIES": 3,
    "RETRY_DELAY": 7,
    "PAUSE": 8,
    "XRAY_IMAGE": IMAGE,
    "XRAY_STARTUP_TIMEOUT": 20,
    "CHROME_PATH": "",
    "CLOSE_BROWSER": True,
    "LOGIN_DIRECT": True,
}


def settings_from_env(args, env):
    """CLI > .env > built-in defaults, applied to all runtime controls."""
    mapping = {
        "profile": ("PROFILE_DIR", str),
        "output": ("OUTPUT_DIR", str),
        "socks_port": ("SOCKS_PORT", int),
        "timeout": ("TIMEOUT", int),
        "answer_wait": ("ANSWER_WAIT", int),
        "response_stable": ("RESPONSE_STABLE", float),
        "ready_wait": ("READY_WAIT", int),
        "retries": ("RETRIES", int),
        "retry_delay": ("RETRY_DELAY", float),
        "pause": ("PAUSE", float),
        "xray_image": ("XRAY_IMAGE", str),
        "xray_startup_timeout": ("XRAY_STARTUP_TIMEOUT", int),
        "chrome_path": ("CHROME_PATH", str),
    }
    for attribute, (key, cast) in mapping.items():
        current = getattr(args, attribute, None)
        if current is not None:
            value = current
        else:
            try:
                value = cast(env.get(key, DEFAULTS[key]))
            except (ValueError, TypeError):
                raise ValueError(f"{key} must be a valid {cast.__name__}")
        setattr(args, attribute, value)
    if args.login_direct is None:
        value = str(env.get("LOGIN_DIRECT", "true")).strip().lower()
        if value not in ("true", "false", "1", "0", "yes", "no", "on", "off"):
            raise ValueError("LOGIN_DIRECT must be true or false")
        args.login_direct = value in ("true", "1", "yes", "on")
    if args.close_browser is None:
        val = str(env.get("CLOSE_BROWSER", "true")).strip().lower()
        if val not in ("true", "false", "1", "0", "yes", "no", "on", "off"):
            raise ValueError("CLOSE_BROWSER must be true or false")
        args.close_browser = val in ("true", "1", "yes", "on")
    if args.retries < 1:
        raise ValueError("RETRIES must be at least 1")
    for key in ("timeout", "answer_wait", "ready_wait", "xray_startup_timeout"):
        if getattr(args, key) < 1:
            raise ValueError(f"{key.upper()} must be at least 1")
    if args.response_stable < 0 or args.pause < 0 or args.retry_delay < 0:
        raise ValueError("RESPONSE_STABLE, PAUSE and RETRY_DELAY cannot be negative")
    if not 1024 <= args.socks_port <= 65535:
        raise ValueError("SOCKS_PORT must be between 1024 and 65535")
    if not args.xray_image.strip():
        raise ValueError("XRAY_IMAGE cannot be empty")
    return args


def main():
    p = argparse.ArgumentParser(description="Browser audit using VLESS or subscription from .env")
    p.add_argument("--env", default=".env", help="Local .env file (ignored by git)")
    p.add_argument("--ports", default=None, help="Override PORTS, e.g. 21001-21009,23001,23004,25001-25025")
    p.add_argument("--profile", default=None, help="Chrome profile (PROFILE_DIR in .env)")
    p.add_argument("--output", default=None, help="Report directory (OUTPUT_DIR in .env)")
    p.add_argument("--socks-port", type=int, default=None)
    p.add_argument("--timeout", type=int, default=None)
    p.add_argument("--answer-wait", type=int, default=None)
    p.add_argument("--response-stable", type=float, default=None)
    p.add_argument("--ready-wait", type=int, default=None)
    p.add_argument("--retries", type=int, default=None)
    p.add_argument("--retry-delay", type=float, default=None)
    p.add_argument("--pause", type=float, default=None)
    p.add_argument("--xray-image", default=None)
    p.add_argument("--xray-startup-timeout", type=int, default=None)
    p.add_argument("--chrome-path", default=None)
    p.add_argument("--login-direct", dest="login_direct", action="store_true",
                   help="Open Chrome without Xray for Google sign-in before testing")
    p.add_argument("--skip-direct-login", dest="login_direct", action="store_false",
                   help="Skip direct login phase, use an existing profile")
    p.add_argument("--close-browser", dest="close_browser", action="store_true")
    p.add_argument("--keep-browser", dest="close_browser", action="store_false")
    p.set_defaults(close_browser=None, login_direct=None)
    args = p.parse_args()
    env = read_env(args.env)
    try:
        settings_from_env(args, env)
    except ValueError as exc:
        p.error(str(exc))

    chrome = args.chrome_path or chrome_bin()
    if not chrome:
        p.error("Google Chrome must be installed")
    if not shutil.which("docker"):
        p.error("Docker must be installed and running")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        p.error("Playwright required: pip install -r requirements.txt")

    try:
        targets, skipped = targets_from_env(env, args.ports)
        if not targets:
            p.error("No supported VLESS entries found")
    except (ValueError, OSError) as exc:
        p.error(str(exc))

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    profile = Path(args.profile).resolve()
    profile.mkdir(parents=True, exist_ok=True)
    profile.chmod(0o700)

    banner("XRAY GEMINI BROWSER AUDIT", [
        f"Mode: {env.get('MODE','vless')} | tests: {len(targets)} | skipped: {len(skipped)}",
        f"Retries: {args.retries} | Answer wait: {args.answer_wait}s",
        f"Pre-submit: {args.ready_wait}s max | Answer: {args.answer_wait}s",
        f"Navigation cap: {args.timeout}s | Stable: {args.response_stable}s",
        f"Close Chrome automatically: {args.close_browser}",
        "Sources stay in local .env only; no credentials are committed.",
        "Only Gemini Web behavior is being tested, not Android.",
    ], CYAN)
    for index, protocol, reason in skipped:
        print(f"SKIPPED subscription entry #{index} ({protocol}): {reason}")

    if subprocess.run(["docker", "image", "inspect", args.xray_image], capture_output=True).returncode:
        subprocess.run(["docker", "pull", args.xray_image], check=True)

    # Step 1: normal Chrome without Xray so Google sign-in uses local internet.
    # Step 2: stop that Chrome completely, then reopen the SAME profile with SOCKS.
    browser_process = None
    login_process = None
    rows = []
    cdp_port = free_port()
    first = targets[0]
    try:
        if args.login_direct:
            banner("STEP 1 / 2: GOOGLE LOGIN - NO XRAY PROXY", [
                "Chrome opens DIRECTLY through your normal internet connection.",
                "Sign in to Google/Gemini in that Chrome window.",
                "Verify your account avatar is visible.",
                "Return to this terminal and press ENTER.",
                "This login Chrome will then close before proxy tests start.",
            ], RED)
            login_cmd = [
                chrome, f"--user-data-dir={profile}", "--no-first-run",
                "--no-proxy-server", "--new-window",
                "https://gemini.google.com/app",
            ]
            login_process = subprocess.Popen(
                login_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            try:
                input("\n>>> PRESS ENTER AFTER LOGIN IS COMPLETE <<<\n")
            finally:
                if login_process.poll() is None:
                    login_process.terminate()
                    try:
                        login_process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        login_process.kill()
                        login_process.wait(timeout=5)
                login_process = None
            # Allow Chrome to flush cookies and release its profile lock.
            time.sleep(2)

        banner("STEP 2 / 2: GEMINI TESTS VIA XRAY", [
            "The login window is closed. Starting a new test Chrome via Xray.",
            "You do NOT need to enter Google credentials through the proxy.",
            "If Google signs you out after IP change, results may be LOGIN_REQUIRED.",
            "Leave the test browser open while the tests are running.",
        ], CYAN)
        with Xray(outbound_from_url(first.uri), first.port, args.socks_port,
                  image=args.xray_image, startup_timeout=args.xray_startup_timeout):
            command = [
                chrome, f"--user-data-dir={profile}", "--no-first-run",
                "--remote-debugging-address=127.0.0.1",
                f"--remote-debugging-port={cdp_port}",
                f"--proxy-server=socks5://127.0.0.1:{args.socks_port}",
                "--disable-quic", "--new-window", "https://gemini.google.com/app"
            ]
            browser_process = subprocess.Popen(
                command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if not wait_cdp(browser_process, cdp_port):
                raise RuntimeError(
                    "Cannot attach to test Chrome; close Chrome instances using this profile."
                )

        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
            context = browser.contexts[0]
            page = next((q for q in context.pages if "gemini.google.com" in q.url), None)
            if page is None:
                page = context.new_page()
            page.bring_to_front()
            for index, target in enumerate(targets, 1):
                label = f"{index}_{target.port}"
                attempts = []
                status, detail = "INCONCLUSIVE", "No completed attempts"
                for attempt in range(1, args.retries + 1):
                    try:
                        with Xray(outbound_from_url(target.uri), target.port, args.socks_port,
                                  image=args.xray_image, startup_timeout=args.xray_startup_timeout):
                            # A fresh tab prevents stale document state between
                            # retries; browser profile/session remain the same.
                            test_page = context.new_page()
                            try:
                                attempt_status, attempt_detail = check_gemini(
                                    test_page, args, f"{label}_{attempt}"
                                )
                                try:
                                    test_page.screenshot(
                                        path=str(output / f"{index:04d}_{target.port}_try{attempt}.png"),
                                        timeout=8000
                                    )
                                except Exception:
                                    pass
                            finally:
                                test_page.close()
                    except Exception as exc:
                        msg = str(exc)
                        attempt_status = "RETRYABLE_NETWORK" if (
                            "ERR_NETWORK_CHANGED" in msg or "Timeout" in type(exc).__name__
                            or "timed out" in msg.lower()
                        ) else "TEST_ERROR"
                        attempt_detail = f"{type(exc).__name__}: {msg[:130]}"
                    attempts.append((attempt_status, attempt_detail))
                    if attempt_status in ("WEB_OK", "REGION_BLOCKED"):
                        # An explicit country restriction is definitive for
                        # this browser visit. No benefit in repeating it.
                        break
                    if attempt < args.retries:
                        time.sleep(args.retry_delay)

                status, detail = consolidate(attempts)
                rows.append({
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "index": index, "name": target.name, "port": target.port,
                    "status": status, "detail": detail,
                    "attempts": len(attempts),
                    "attempt_results": ";".join(item[0] for item in attempts)
                })
                log_result(index, len(targets), target, status, detail, len(attempts))
                if index < len(targets):
                    time.sleep(args.pause)
            browser.close()
    except KeyboardInterrupt:
        print("\nInterrupted, saving partial results.", file=sys.stderr)
    finally:
        if login_process is not None and login_process.poll() is None:
            login_process.terminate()
            try:
                login_process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                login_process.kill()
                login_process.wait(timeout=5)
        path = output / "results.csv"
        with path.open("w", newline="", encoding="utf8") as f:
            w = csv.DictWriter(f, fieldnames=["timestamp_utc", "index", "name", "port", "status", "detail", "attempts", "attempt_results"])
            w.writeheader()
            w.writerows(rows)
        print("\nREPORT:", path, flush=True)
        print("WARNING: Changing Xray while Chrome stays open can retain connections.")
        print("Results are candidates only; confirm via screenshots and Android before changing balancers.")
        if browser_process and browser_process.poll() is None:
            if args.close_browser:
                # Only terminate the dedicated Chrome process we started.
                # Never touch the user's ordinary Chrome profile/processes.
                browser_process.terminate()
                try:
                    browser_process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    browser_process.kill()
                    browser_process.wait(timeout=5)
                print("Test Chrome closed automatically; local login profile preserved.")
            else:
                print("Chrome left open (CLOSE_BROWSER=false). Close manually before next run.")


if __name__ == "__main__":
    main()
