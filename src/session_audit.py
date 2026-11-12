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
    # Force a fresh document on every probe. Existing Chrome connections can
    # still survive an Xray restart, so do not infer actual IP from these tests.
    page.goto("https://gemini.google.com/app", wait_until="domcontentloaded",
              timeout=args.timeout * 1000)
    page.wait_for_timeout(3000)
    body = page.locator("body").inner_text(timeout=12000)
    if REGION.search(body):
        return "REGION_BLOCKED", "Gemini Web shows unsupported country"
    if LOGIN.search(body) or page.get_by_text("Sign in", exact=True).count() > 0:
        return "LOGIN_REQUIRED", "Google session missing or security challenge"

    editors = page.locator('[contenteditable="true"]:visible, textarea:visible, [role="textbox"]:visible')
    if not editors.count():
        return "INCONCLUSIVE", "Gemini editor not found; check screenshot"
    marker = f"GEMTEST{label}X".replace("-", "")
    editor = editors.last
    editor.fill(f"Reply with exactly {marker}")
    editor.press("Enter")
    end = time.monotonic() + args.answer_wait
    while time.monotonic() < end:
        page.wait_for_timeout(1500)
        body = page.locator("body").inner_text(timeout=12000)
        if REGION.search(body):
            return "REGION_BLOCKED", "Unsupported country after submission"
        if LOGIN.search(body):
            return "LOGIN_REQUIRED", "Login challenge after submission"
        if body.count(marker) >= 2:
            return "RESPONSE_CANDIDATE", "Response-like text; inspect screenshot before trusting"
    return "INCONCLUSIVE", "No reliable answer before timeout"


def main():
    p = argparse.ArgumentParser(description="Browser audit using VLESS or subscription from .env")
    p.add_argument("--env", default=".env", help="Local .env file (ignored by git)")
    p.add_argument("--ports", default=None, help="Override PORTS, e.g. 21001-21009,23001,23004,25001-25025")
    p.add_argument("--profile", default=".local/browser-profile")
    p.add_argument("--output", default="reports/session")
    p.add_argument("--socks-port", type=int, default=18998)
    p.add_argument("--timeout", type=int, default=35)
    p.add_argument("--answer-wait", type=int, default=45)
    p.add_argument("--pause", type=float, default=4)
    args = p.parse_args()

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
        env = read_env(args.env)
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
            page = next((q for q in context.pages if "gemini.google.com" in q.url), context.new_page())
            for index, target in enumerate(targets, 1):
                status, detail = "TEST_ERROR", ""
                label = f"{index}_{target.port}"
                try:
                    with Xray(outbound_from_url(target.uri), target.port, args.socks_port):
                        try:
                            status, detail = check_gemini(page, args, label)
                        finally:
                            try:
                                page.screenshot(path=str(output / f"{index:04d}_{target.port}.png"),
                                                timeout=8000)
                            except Exception:
                                pass
                except Exception as exc:
                    detail = f"{type(exc).__name__}: {str(exc)[:200]}"
                rows.append({
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "index": index, "name": target.name, "port": target.port,
                    "status": status, "detail": detail
                })
                print(f"[{index:03d}/{len(targets)}] {target.name[:36]} port={target.port} {status} {detail}", flush=True)
                if index < len(targets):
                    time.sleep(args.pause)
            browser.close()
    except KeyboardInterrupt:
        print("\nInterrupted, saving partial results.", file=sys.stderr)
    finally:
        path = output / "results.csv"
        with path.open("w", newline="", encoding="utf8") as f:
            w = csv.DictWriter(f, fieldnames=["timestamp_utc", "index", "name", "port", "status", "detail"])
            w.writeheader()
            w.writerows(rows)
        print("\nREPORT:", path, flush=True)
        print("WARNING: Changing Xray while Chrome stays open can retain connections.")
        print("Results are candidates only; confirm via screenshots and Android before changing balancers.")
        if browser_process and browser_process.poll() is None:
            print("Chrome left open; close it manually before next run.")


if __name__ == "__main__":
    main()
