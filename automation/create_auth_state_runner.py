from __future__ import annotations

import asyncio

from automation.playwright_runner import (
    _ensure_invite_flow_ready,
    _is_auth_required,
    validate_workspace_auth,
)
from config import ChatGPTWorkspaceConfig, Settings
from utils.logger import get_logger


async def capture_workspace_profile(
    workspace: ChatGPTWorkspaceConfig,
    settings: Settings,
    *,
    confirmation_event: asyncio.Event,
) -> tuple[ChatGPTWorkspaceConfig, str | None]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - depends on local install
        raise RuntimeError(f"Playwright is not installed: {exc}") from exc

    if workspace.profile_dir is None:
        raise RuntimeError("Workspace onboarding requires a profile_dir")

    logger = get_logger("automation.auth_state_capture")
    workspace.profile_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(workspace.profile_dir),
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context.set_default_timeout(settings.playwright_action_timeout_ms)
        context.set_default_navigation_timeout(settings.playwright_navigation_timeout_ms)
        page = next((item for item in context.pages if (item.url or "").strip() not in {"", "about:blank"}), None)
        if page is None:
            page = await context.new_page()

        try:
            await page.goto(workspace.workspace_url, wait_until="domcontentloaded")
            await asyncio.wait_for(
                confirmation_event.wait(),
                timeout=max(60, settings.playwright_onboarding_timeout_sec),
            )
            await page.wait_for_timeout(1000)

            current_url = page.url or workspace.workspace_url
            members_url = workspace.members_url
            if not members_url and not await _is_auth_required(page):
                try:
                    await _ensure_invite_flow_ready(page, settings, workspace, logger, label="local_capture")
                    members_url = page.url or None
                except Exception:
                    logger.info("Invite area was not reached during capture for %s", workspace.id)

            workspace_url = current_url.split("/members", 1)[0] if "/members" in current_url else current_url
        finally:
            await context.close()

    return (
        ChatGPTWorkspaceConfig(
            id=workspace.id,
            name=workspace.name,
            workspace_url=workspace_url or workspace.workspace_url,
            profile_dir=workspace.profile_dir,
            members_url=members_url,
            max_users=workspace.max_users,
            enabled=True,
            source=workspace.source,
            db_id=workspace.db_id,
        ),
        members_url,
    )


async def capture_and_validate_workspace(
    workspace: ChatGPTWorkspaceConfig,
    settings: Settings,
    *,
    confirmation_event: asyncio.Event,
):
    captured_workspace, _ = await capture_workspace_profile(
        workspace,
        settings,
        confirmation_event=confirmation_event,
    )
    return await validate_workspace_auth(captured_workspace, settings)
