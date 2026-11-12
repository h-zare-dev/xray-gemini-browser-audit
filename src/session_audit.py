#!/usr/bin/env python3
"""Gemini Web test on a single, normally launched Chrome process.

Chrome remains running throughout the tests. Xray is official Docker image.
This is experimental: Google may reject sign-in or challenge a session.
"""
import argparse
import csv
import getpass
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time

from audit import Xray, load_ports, choose_ports, IMAGE
from vless import outbound_from_url

REGION = re.compile(r"this country isn.t supported|not available in your country|isn't available in your country|not available in your region", re.I)
LOGIN = re.compile(r"sign in to save activity|sign in to connect to google apps|couldn.t sign you in|verify it.s you", re.I)


def chrome_bin():
    return shutil.which("google-chrome-stable") or shutil.which("google-chrome")


def wait_cdp(process, timeout=25):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if process.poll() is not None:
            return False
        try:
            with socket.create_connection(("127.0.0.1", 9222), 0.3):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def check_gemini(page, args, port):
    page.goto("https://gemini.google.com/app", wait_until="domcontentloaded",
              timeout=args.timeout * 1000)
    page.wait_for_timeout(3500)
    body = page.locator("body").inner_text(timeout=12000)
    if REGION.search(body):
        return "REGION_BLOCKED", "Gemini Web country restriction"
    if LOGIN.search(body):
        return "LOGIN_REQUIRED", "Google account signed out or security challenge"
    # Never classify anonymous Gemini as success.
    if page.get_by_text("Sign in", exact=True).count() > 0:
        return "LOGIN_REQUIRED", "Gemini is in guest mode"

    editors = page.locator('[contenteditable="true"]:visible, textarea:visible, [role="textbox"]:visible')
    if not editors.count():
        return "INCONCLUSIVE", "Gemini editor unavailable"
    marker = f"GEMTEST{port}X"
    editor = editors.last
    editor.fill(f"Reply with exactly {marker}")
    editor.press("Enter")
    end = time.monotonic() + args.answer_wait
    while time.monotonic() < end:
        page.wait_for_timeout(1500)
        body = page.locator("body").inner_text(timeout=12000)
        if REGION.search(body):
            return "REGION_BLOCKED", "Unsupported country after sending message"
        if LOGIN.search(body):
            return "LOGIN_REQUIRED", "Session expired or Google challenge"
        if body.count(marker) >= 2:
            return "RESPONSE_CANDIDATE", "Response marker found, inspect screenshot"
    return "INCONCLUSIVE", "No verifiable response within deadline"


def main():
    p = argparse.ArgumentParser(description="Audit Gemini Web through one persistent real Chrome window")
    p.add_argument("--ports", default="23001,23004,23007")
    p.add_argument("--port-map", default="data/ports.csv")
    p.add_argument("--profile", default=".local/browser-profile")
    p.add_argument("--output", default="reports/session")
    p.add_argument("--socks-port", type=int, default=18998)
    p.add_argument("--timeout", type=int, default=35)
    p.add_argument("--answer-wait", type=int, default=45)
    p.add_argument("--pause", type=float, default=4)
    args = p.parse_args()

    chrome = chrome_bin()
    if not chrome:
        p.error("Official Google Chrome required")
    if not shutil.which("docker"):
        p.error("Docker required")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        p.error("Install Playwright using requirements.txt")

    mapping = load_ports(args.port_map)
    ports = choose_ports(args.ports, mapping)
    uri = getpass.getpass("Paste VLESS link (hidden; not saved): ")
    outbound = outbound_from_url(uri)
    if subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode:
        subprocess.run(["docker", "pull", IMAGE], check=True)

    profile = Path(args.profile).resolve()
    profile.mkdir(parents=True, exist_ok=True)
    profile.chmod(0o700)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    # Only one browser process and a single persistent authenticated context
    # throughout the port changes.
    first = ports[0]
    browser_process = None
    result_rows = []
    try:
        with Xray(outbound, first, args.socks_port):
            cmd = [
                chrome, f"--user-data-dir={profile}", "--no-first-run",
                "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=9222",
                f"--proxy-server=socks5://127.0.0.1:{args.socks_port}",
                "--disable-quic", "--new-window",
                "https://gemini.google.com/app",
            ]
            print("Opening NORMAL Chrome connected to SOCKS via Xray.", flush=True)
            print("Sign in manually. Keep this browser OPEN for the whole test.", flush=True)
            browser_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                               stderr=subprocess.DEVNULL)
            if not wait_cdp(browser_process):
                raise RuntimeError("Cannot connect to normal Chrome debug port 9222; close other Chrome test instances")
            input("When signed in and Gemini answers a test prompt, press Enter HERE: ")

        # Chrome stays alive, so its login and device context persist while
        # only the proxy backend Xray container changes destination port.
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = browser.contexts[0]
            page = next((q for q in context.pages if "gemini.google.com" in q.url),
                        context.new_page())
            for i, port in enumerate(ports, 1):
                status, detail = "TEST_ERROR", ""
                try:
                    with Xray(outbound, port, args.socks_port):
                        try:
                            status, detail = check_gemini(page, args, port)
                        finally:
                            try:
                                page.screenshot(path=str(output / f"{port}.png"),
                                                full_page=False, timeout=8000)
                            except Exception:
                                pass
                except Exception as e:
                    detail = f"{type(e).__name__}: {str(e)[:180]}"
                result_rows.append({
                    "port": port, "country": mapping[port]["country"],
                    "outbound": mapping[port]["outbound_tag"],
                    "status": status, "detail": detail
                })
                print(f"[{i}/{len(ports)}] {port} {mapping[port]['outbound_tag']} {status}: {detail}", flush=True)
                if i < len(ports):
                    time.sleep(args.pause)
            browser.close()
    except KeyboardInterrupt:
        print("\nInterrupted; writing partial results.", file=sys.stderr)
    finally:
        with (output / "results.csv").open("w", encoding="utf8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["port", "country", "outbound", "status", "detail"])
            writer.writeheader()
            writer.writerows(result_rows)
        print("Report:", output / "results.csv", flush=True)
        if browser_process is not None and browser_process.poll() is None:
            print("Chrome was left open. Close the test window manually; profile is local only.", flush=True)


if __name__ == "__main__":
    main()
