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
REGION = re.compile(r"this country isn.t supported|not available in your country|isn't available in your country|not available in your region", re.I)
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
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    try:
        page.goto("https://gemini.google.com/app", wait_until="domcontentloaded",
                  timeout=args.timeout * 1000)
    except PlaywrightTimeoutError:
        return "RETRYABLE_NETWORK", "Page load timed out; will retry"
    except Exception as exc:
        if "ERR_NETWORK_CHANGED" in str(exc) or "ERR_CONNECTION" in str(exc):
            return "RETRYABLE_NETWORK", "Network changed during port switch; will retry"
        raise

    # Wait for a useful ready state instead of using a fixed 3-second sleep.
    selectors = '[contenteditable="true"]:visible, textarea:visible, [role="textbox"]:visible'
    until = time.monotonic() + args.ready_wait
    body = ""
    editors = page.locator(selectors)
    while time.monotonic() < until:
        try:
            body = page.locator("body").inner_text(timeout=5000)
            if REGION.search(body):
                return "REGION_BLOCKED", "Gemini Web explicitly says country unsupported"
            if LOGIN.search(body) or page.get_by_text("Sign in", exact=True).count() > 0:
                return "LOGIN_REQUIRED", "Google account signed out or verification required"
            if editors.count() > 0:
                break
        except Exception:
            pass
        page.wait_for_timeout(1000)
    else:
        return "INCONCLUSIVE", "Prompt editor not ready after waiting for page"

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
    if status == "REGION_BLOCKED_CONFIRMED":
        return RED, "BLOCKED"
    if status == "CONNECTION_FAILED_CONFIRMED":
        return RED, "NETWORK ERROR"
    return YELLOW, "CHECK"


def consolidate(attempts):
    """Never turn a transient or mixed result into a confirmed failure."""
    states = [row[0] for row in attempts]
    if "WEB_OK" in states:
        return "WEB_OK", "Received a verified model response"
    if len(states) >= 3 and all(st == "REGION_BLOCKED" for st in states):
        return "REGION_BLOCKED_CONFIRMED", "Country restriction repeated on 3 attempts"
    if len(states) >= 3 and all(st == "RETRYABLE_NETWORK" for st in states):
        return "CONNECTION_FAILED_CONFIRMED", "Network failed on all 3 attempts"
    if "LOGIN_REQUIRED" in states:
        return "LOGIN_REQUIRED", "Google login/security challenge: manual review needed"
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


def main():
    p = argparse.ArgumentParser(description="Browser audit using VLESS or subscription from .env")
    p.add_argument("--env", default=".env", help="Local .env file (ignored by git)")
    p.add_argument("--ports", default=None, help="Override PORTS, e.g. 21001-21009,23001,23004,25001-25025")
    p.add_argument("--profile", default=".local/browser-profile")
    p.add_argument("--output", default="reports/session")
    p.add_argument("--socks-port", type=int, default=18998)
    p.add_argument("--timeout", type=int, default=55)
    p.add_argument("--answer-wait", type=int, default=None,
                   help="Gemini response wait seconds (CLI > ANSWER_WAIT in .env > 70)")
    p.add_argument("--response-stable", type=float, default=4,
                   help="Seconds the assistant answer must remain stable before success")
    p.add_argument("--ready-wait", type=int, default=25,
                   help="Wait for Gemini editor to load (seconds)")
    p.add_argument("--retries", type=int, default=None,
                   help="Attempts for uncertain/error results (CLI > RETRIES in .env > 3)")
    p.add_argument("--retry-delay", type=float, default=7,
                   help="Seconds between retry attempts")
    p.add_argument("--pause", type=float, default=8)
    args = p.parse_args()

    # CLI arguments override .env; .env overrides built-in defaults.
    env = read_env(args.env)
    try:
        args.retries = (
            args.retries if args.retries is not None
            else int(env.get("RETRIES", "3"))
        )
        args.answer_wait = (
            args.answer_wait if args.answer_wait is not None
            else int(env.get("ANSWER_WAIT", "70"))
        )
    except ValueError:
        p.error("RETRIES and ANSWER_WAIT must be integer numbers")
    if args.retries < 3:
        p.error("RETRIES must be at least 3")
    if args.answer_wait < 1:
        p.error("ANSWER_WAIT must be at least 1 second")

    chrome = chrome_bin()
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
        "Sources stay in local .env only; no credentials are committed.",
        "Only Gemini Web behavior is being tested, not Android.",
    ], CYAN)
    for index, protocol, reason in skipped:
        print(f"SKIPPED subscription entry #{index} ({protocol}): {reason}")

    if subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode:
        subprocess.run(["docker", "pull", IMAGE], check=True)

    # Bootstrap through first source; require user to verify Gemini before tests.
    browser_process = None
    rows = []
    cdp_port = free_port()
    first = targets[0]
    try:
        with Xray(outbound_from_url(first.uri), first.port, args.socks_port):
            command = [
                chrome, f"--user-data-dir={profile}", "--no-first-run",
                "--remote-debugging-address=127.0.0.1",
                f"--remote-debugging-port={cdp_port}",
                f"--proxy-server=socks5://127.0.0.1:{args.socks_port}",
                "--disable-quic", "--new-window", "https://gemini.google.com/app"
            ]
            browser_process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if not wait_cdp(browser_process, cdp_port):
                raise RuntimeError("Cannot attach to Chrome. Close other Chrome windows using this test profile.")

            banner("ACTION REQUIRED: SIGN IN TO GEMINI", [
                "1. Go to the Chrome window that just opened.",
                "2. Sign in to your Google account MANUALLY.",
                "3. Send a test message and verify Gemini answers.",
                "4. KEEP CHROME OPEN, come back to this terminal.",
                "5. Press ENTER below to start the tests.",
            ], RED)
            input("\n" + (GREEN if sys.stdout.isatty() else "") +
                  ">>> AFTER YOU HAVE SIGNED IN, PRESS ENTER TO START <<<" + RESET + "\n")

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
                        with Xray(outbound_from_url(target.uri), target.port, args.socks_port):
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
                    if attempt_status == "WEB_OK":
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
        path = output / "results.csv"
        with path.open("w", newline="", encoding="utf8") as f:
            w = csv.DictWriter(f, fieldnames=["timestamp_utc", "index", "name", "port", "status", "detail", "attempts", "attempt_results"])
            w.writeheader()
            w.writerows(rows)
        print("\nREPORT:", path, flush=True)
        print("WARNING: Changing Xray while Chrome stays open can retain connections.")
        print("Results are candidates only; confirm via screenshots and Android before changing balancers.")
        if browser_process and browser_process.poll() is None:
            print("Chrome left open; close it manually before next run.")


if __name__ == "__main__":
    main()
