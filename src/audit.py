#!/usr/bin/env python3
"""Gemini Web browser audit through official Xray Core inside Docker.

Prototype. No modifications to a user's Xray server, PasarGuard, or balancers.
"""
import argparse
import csv
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from vless import outbound_from_url, xray_config

IMAGE = "ghcr.io/xtls/xray-core:26.3.27"
REGION = re.compile(r"this country isn.t supported|gemini isn.t available in your country|not available in your region|isn't supported in your country", re.I)
CHALLENGE = re.compile(r"verify it.s you|verify your identity|sign in|captcha|unusual activity", re.I)


def load_ports(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    ports = {int(row["test_port"]): row for row in rows}
    if len(ports) != 61:
        print(f"WARNING: expected 61 ports, found {len(ports)}", file=sys.stderr)
    return ports


def choose_ports(spec, mapping):
    if not spec:
        return sorted(mapping)
    selected = []
    for item in spec.split(","):
        if "-" in item:
            lo, hi = map(int, item.split("-", 1))
            selected.extend(range(lo, hi + 1))
        else:
            selected.append(int(item))
    selected = list(dict.fromkeys(selected))
    if not set(selected).issubset(mapping):
        raise ValueError("Unknown port in --ports")
    return selected


def wait_listen(port, process, timeout=20):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if process.poll() is not None:
            return False
        try:
            with socket.create_connection(("127.0.0.1", port), 0.4):
                return True
        except OSError:
            time.sleep(0.2)
    return False


class Xray:
    def __init__(self, outbound, destination, socks_port):
        self.outbound = outbound
        self.destination = destination
        self.socks_port = socks_port
        self.container = f"gemini-audit-{os.getpid()}-{destination}"
        self.process = None
        self.tmp = None
        self.log_file = None

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="gemini-xray-")
        conf = Path(self.tmp.name) / "config.json"
        conf.write_text(json.dumps(xray_config(self.outbound, self.destination, self.socks_port)), encoding="utf8")
        conf.chmod(0o644)
        command = [
            "docker", "run", "--rm", "--pull=never", "--name", self.container,
            "--network=bridge", "-p", f"127.0.0.1:{self.socks_port}:{self.socks_port}/tcp",
            "--mount", f"type=bind,source={conf.resolve()},target=/tmp/config.json,readonly",
            "--cap-drop=ALL", "--security-opt", "no-new-privileges",
            "--entrypoint", "/usr/local/bin/xray", IMAGE, "run", "-c", "/tmp/config.json"
        ]
        self.log_file = open(Path(self.tmp.name) / "xray.log", "w")
        self.process = subprocess.Popen(command, stdout=self.log_file, stderr=subprocess.STDOUT)
        if not wait_listen(self.socks_port, self.process):
            self.__exit__(None, None, None)
            raise RuntimeError("Xray SOCKS not available; check Docker and image")
        return self

    def __exit__(self, *_):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        subprocess.run(["docker", "rm", "-f", self.container], capture_output=True, timeout=12)
        if self.log_file:
            self.log_file.close()
        if self.tmp:
            self.tmp.cleanup()


def browser_test(playwright, args, port, login=False):
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(Path(args.profile).resolve()),
        channel="chrome",
        headless=not (args.headed or login),
        proxy={"server": f"socks5://127.0.0.1:{args.socks_port}"},
        viewport={"width": 1280, "height": 900},
        args=["--disable-quic"], timeout=30000
    )
    page = None
    try:
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(12000)
        page.goto("https://gemini.google.com/app", wait_until="domcontentloaded", timeout=args.timeout * 1000)
        page.wait_for_timeout(2500)
        if login:
            print("Sign in manually. After you see Gemini, return here and press Enter.")
            input("Press Enter to save the browser profile: ")
            return "LOGIN_FINISHED", "Manual login flow complete"
        body = page.locator("body").inner_text(timeout=12000)
        if REGION.search(body):
            return "REGION_BLOCKED", "Unsupported country message on Gemini Web"
        fields = page.locator('[contenteditable="true"]:visible, textarea:visible, [role="textbox"]:visible')
        if fields.count() == 0:
            return ("LOGIN_OR_CHALLENGE" if CHALLENGE.search(body) else "INCONCLUSIVE",
                    "No visible prompt editor; sign-in, challenge, or UI change")
        marker = "ORANGE-7429"
        field = fields.last
        before = body
        field.fill("Reply with exactly " + marker)
        field.press("Enter")
        end = time.monotonic() + args.answer_wait
        while time.monotonic() < end:
            page.wait_for_timeout(1500)
            body = page.locator("body").inner_text(timeout=12000)
            if REGION.search(body):
                return "REGION_BLOCKED", "Unsupported country message after submit"
            if CHALLENGE.search(body) and not CHALLENGE.search(before):
                return "LOGIN_OR_CHALLENGE", "Sign-in challenge during generation"
            # Conservative heuristic; a repeated marker can be echoed by the UI.
            if body.count(marker) >= 2:
                return "WEB_RESPONSE_DETECTED", "Response marker appeared twice; verify screenshot"
        return "INCONCLUSIVE", "No reliable generated answer before timeout"
    finally:
        if page is not None and not login:
            try:
                Path(args.output).mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(Path(args.output) / f"{port}.png"), timeout=8000)
            except Exception:
                pass
        context.close()


def main():
    parser = argparse.ArgumentParser(description="Gemini Web browser audit via VLESS + Docker Xray + Playwright")
    parser.add_argument("--port-map", default="data/ports.csv")
    parser.add_argument("--ports", help="Comma-separated ports, optionally ranges")
    parser.add_argument("--login", action="store_true")
    parser.add_argument("--login-port", type=int, default=23007)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--profile", default=".local/browser-profile")
    parser.add_argument("--output", default="reports")
    parser.add_argument("--socks-port", type=int, default=18998)
    parser.add_argument("--timeout", type=int, default=35)
    parser.add_argument("--answer-wait", type=int, default=40)
    parser.add_argument("--pause", type=float, default=5)
    args = parser.parse_args()
    if args.login:
        # Google may block OAuth in an automated browser. Sign in using normal
        # Chrome first, not through Playwright, without saving any credentials.
        login_script = Path(__file__).with_name("login.py")
        raise SystemExit(subprocess.call([sys.executable, str(login_script), "--profile", args.profile]))
    if not shutil.which("docker"):
        parser.error("Docker required; Xray need not be installed on host")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        parser.error("Install playwright: pip install -r requirements.txt; python -m playwright install chromium")
    mapping = load_ports(args.port_map)
    chosen = [args.login_port] if args.login else choose_ports(args.ports, mapping)
    if not set(chosen).issubset(mapping):
        parser.error("Invalid test port")
    link = getpass.getpass("Paste VLESS link (hidden, not stored): ")
    outbound = outbound_from_url(link)
    if subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode:
        subprocess.run(["docker", "pull", IMAGE], check=True)
    Path(args.output).mkdir(parents=True, exist_ok=True)
    rows = []
    try:
        with sync_playwright() as playwright:
            for index, port in enumerate(chosen, 1):
                info = mapping[port]
                entry = {
                    "time_utc": datetime.now(timezone.utc).isoformat(),
                    "port": port, "country": info["country"], "outbound": info["outbound_tag"],
                    "status": "INCONCLUSIVE", "detail": ""
                }
                try:
                    with Xray(outbound, port, args.socks_port):
                        status, detail = browser_test(playwright, args, port, login=args.login)
                        entry.update(status=status, detail=detail)
                except KeyboardInterrupt:
                    print("\nInterrupted")
                    break
                except Exception as exc:
                    entry.update(status="TEST_ERROR", detail=f"{type(exc).__name__}: {str(exc)[:240]}")
                rows.append(entry)
                print(f"[{index:02d}/{len(chosen)}] {port} {info['outbound_tag']} {entry['status']} {entry['detail']}", flush=True)
                if not args.login and index != len(chosen):
                    time.sleep(args.pause)
    finally:
        path = Path(args.output) / "results.csv"
        with path.open("w", newline="", encoding="utf8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["time_utc", "port", "country", "outbound", "status", "detail"])
            writer.writeheader()
            writer.writerows(rows)
        print("Report:", path)
        print("Browser success does not guarantee Gemini Android success. Review screenshots before changing balancers.")


if __name__ == "__main__":
    main()
