from playwright.sync_api import sync_playwright
import os
from pathlib import Path

PROFILE_DIR = Path("automation/auth_state/chrome_profiles/manual")
os.makedirs(PROFILE_DIR, exist_ok=True)

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        str(PROFILE_DIR),
        headless=False,
        channel="chrome",  # важно
        args=["--disable-blink-features=AutomationControlled"]
    )

    page = context.new_page()
    page.goto("https://chatgpt.com/", wait_until="domcontentloaded")

    print("Войди в аккаунт и нажми Enter")
    input()

    context.close()