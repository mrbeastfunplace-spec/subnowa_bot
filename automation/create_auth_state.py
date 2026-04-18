import os
from pathlib import Path

from playwright.sync_api import sync_playwright

PROFILE_DIR = Path(os.getenv("PLAYWRIGHT_PROFILE_DIR", "automation/auth_state/chrome_profile"))

os.makedirs(PROFILE_DIR, exist_ok=True)

with sync_playwright() as p:
    print("Используется профиль:", PROFILE_DIR)
    context = p.chromium.launch_persistent_context(
        str(PROFILE_DIR),
        headless=False,
        viewport={"width": 1366, "height": 900},
        args=["--disable-blink-features=AutomationControlled"]
    )

    page = context.new_page()
    page.goto("https://chatgpt.com/", wait_until="domcontentloaded")

    print("Войди в аккаунт вручную. После полного входа нажми Enter в терминале.")
    input()

    print("Профиль сохранён в:", PROFILE_DIR)
    context.close()
