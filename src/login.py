#!/usr/bin/env python3
"""Open ordinary Google Chrome for manual sign-in, without Playwright or Docker.

This does not bypass Google sign-in security. Profile remains on this machine.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="Manual sign-in in a standard Chrome process")
    parser.add_argument("--profile", default=".local/browser-profile")
    args = parser.parse_args()
    chrome = shutil.which("google-chrome-stable") or shutil.which("google-chrome")
    if not chrome:
        parser.error("Google Chrome is required; install official Chrome (not Playwright Chromium)")
    profile = Path(args.profile).resolve()
    profile.mkdir(parents=True, exist_ok=True)
    profile.chmod(0o700)
    print("Opening normal Google Chrome with a separate local profile.")
    print("Sign in manually at https://gemini.google.com/app and close this Chrome window when finished.")
    print("No Google password, API key, VLESS URL or cookie is sent to GitHub.")
    print("Do NOT run this simultaneously with the audit using the same profile.")
    code = subprocess.call([chrome, f"--user-data-dir={profile}", "--no-first-run",
                            "--new-window", "https://gemini.google.com/app"])
    if code:
        print(f"Chrome exited with code {code}", file=sys.stderr)
        sys.exit(code)
    print("Chrome closed; profile saved locally. Sign-in may still be restricted by Google.")


if __name__ == "__main__":
    main()
