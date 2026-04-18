from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from automation.selectors import (
    AUTH_INPUT_SELECTORS,
    DUPLICATE_HINT_SELECTORS,
    INVITE_BUTTON_SELECTORS,
    INVITE_DIALOG_SELECTORS,
    INVITE_EMAIL_INPUT_SELECTORS,
    INVITE_SUBMIT_SELECTORS,
    MEMBER_COUNT_SELECTORS,
    MEMBER_ROW_SELECTORS,
    MEMBER_SECTION_SELECTORS,
    MEMBERS_NAV_SELECTORS,
    PENDING_ROW_SELECTORS,
    SUCCESS_MESSAGE_SELECTORS,
)
from config import ChatGPTWorkspaceConfig, Settings
from utils.logger import get_logger


PlaywrightResultStatus = Literal[
    "invited",
    "already_invited",
    "no_workspace_available",
    "profile_not_found",
    "auth_failed",
    "invite_failed",
    "unexpected_error",
]


@dataclass(slots=True)
class PlaywrightInviteResult:
    status: PlaywrightResultStatus
    workspace_id: str | None = None
    workspace_name: str | None = None
    member_count: int | None = None
    error_message: str | None = None


class _AuthFailedError(Exception):
    pass


class _DuplicateInviteError(Exception):
    def __init__(self, message: str, member_count: int | None = None) -> None:
        super().__init__(message)
        self.member_count = member_count


class _WorkspaceFullError(Exception):
    def __init__(self, member_count: int | None = None) -> None:
        super().__init__("Workspace member limit reached")
        self.member_count = member_count


class _TransientInviteError(Exception):
    pass


class _InviteFailedError(Exception):
    pass


def _result(
    status: PlaywrightResultStatus,
    workspace: ChatGPTWorkspaceConfig,
    *,
    member_count: int | None = None,
    error_message: str | None = None,
) -> PlaywrightInviteResult:
    return PlaywrightInviteResult(
        status=status,
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        member_count=member_count,
        error_message=error_message,
    )


async def _locator_text(locator) -> str:
    try:
        return (await locator.inner_text()).strip()
    except Exception:
        return ""


async def _wait_for_first(page, selectors: tuple[str, ...], timeout: int):
    last_error: Exception | None = None
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(state="visible", timeout=timeout)
            return locator
        except Exception as exc:
            last_error = exc
    raise _TransientInviteError(f"Element was not found for selectors: {selectors}") from last_error


async def _click_first(page, selectors: tuple[str, ...], timeout: int) -> None:
    locator = await _wait_for_first(page, selectors, timeout)
    try:
        await locator.click(timeout=timeout)
    except Exception as exc:
        raise _TransientInviteError("Click action failed") from exc


async def _fill_first(page, selectors: tuple[str, ...], value: str, timeout: int) -> None:
    locator = await _wait_for_first(page, selectors, timeout)
    try:
        await locator.fill(value, timeout=timeout)
    except Exception as exc:
        raise _TransientInviteError("Failed to fill invite email") from exc


async def _contains_email(page, email: str) -> bool:
    target = email.lower()
    for selector_group in (MEMBER_SECTION_SELECTORS, INVITE_DIALOG_SELECTORS):
        for selector in selector_group:
            locator = page.locator(selector).first
            try:
                text = (await locator.inner_text(timeout=1000)).lower()
            except Exception:
                continue
            if target in text:
                return True
    try:
        body_text = (await page.locator("body").inner_text(timeout=1500)).lower()
    except Exception:
        return False
    return target in body_text


async def _has_duplicate_hint(page) -> bool:
    for selector in DUPLICATE_HINT_SELECTORS:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(state="visible", timeout=700)
            return True
        except Exception:
            continue
    return False


async def _is_auth_required(page) -> bool:
    current_url = (page.url or "").lower()
    if any(marker in current_url for marker in ("login", "signin", "auth")):
        return True
    for selector in AUTH_INPUT_SELECTORS:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(state="visible", timeout=700)
            return True
        except Exception:
            continue
    return False


async def _ensure_members_page(page, workspace: ChatGPTWorkspaceConfig, settings: Settings) -> None:
    if workspace.members_url:
        try:
            await page.goto(workspace.members_url, wait_until="domcontentloaded")
        except Exception as exc:
            raise _TransientInviteError("Members page did not load") from exc
    else:
        for selector in MEMBER_SECTION_SELECTORS:
            try:
                await page.locator(selector).first.wait_for(state="visible", timeout=1500)
                return
            except Exception:
                continue
        await _click_first(page, MEMBERS_NAV_SELECTORS, settings.playwright_action_timeout_ms)
    await _wait_for_first(page, MEMBER_SECTION_SELECTORS, settings.playwright_action_timeout_ms)


async def _extract_member_count(page) -> int | None:
    for selector in MEMBER_COUNT_SELECTORS:
        locator = page.locator(selector).first
        try:
            text = await _locator_text(locator)
        except Exception:
            continue
        match = re.search(r"(\d+)", text)
        if match:
            return int(match.group(1))
    for selector in MEMBER_ROW_SELECTORS:
        try:
            count = await page.locator(selector).count()
        except Exception:
            continue
        if count > 0:
            return count
    return None


async def _wait_for_success(page, timeout: int, email: str) -> bool:
    for selector in SUCCESS_MESSAGE_SELECTORS:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            continue
    try:
        await page.wait_for_timeout(1200)
    except Exception:
        return False
    return await _contains_email(page, email)


async def _run_once(workspace: ChatGPTWorkspaceConfig, email: str, settings: Settings) -> PlaywrightInviteResult:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - depends on local install
        return _result("unexpected_error", workspace, error_message=f"Playwright is not installed: {exc}")

    logger = get_logger("automation.playwright")
    logger.info(
        "Using Playwright persistent profile dir | workspace=%s profile_dir=%s",
        workspace.id,
        workspace.profile_dir,
    )
    if not workspace.profile_dir.exists():
        return _result(
            "profile_not_found",
            workspace,
            error_message=f"Persistent profile directory was not found: {workspace.profile_dir}",
        )

    async with async_playwright() as playwright:
        logger.info(
            "Launching Playwright persistent context | workspace=%s profile_dir=%s",
            workspace.id,
            workspace.profile_dir,
        )
        context = await playwright.chromium.launch_persistent_context(
            str(workspace.profile_dir),
            headless=settings.playwright_headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context.set_default_timeout(settings.playwright_action_timeout_ms)
        context.set_default_navigation_timeout(settings.playwright_navigation_timeout_ms)
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            await page.goto(workspace.workspace_url, wait_until="domcontentloaded")
        except Exception as exc:
            raise _TransientInviteError("Workspace page did not load") from exc

        try:
            if await _is_auth_required(page):
                raise _AuthFailedError("Persistent profile is no longer authenticated")

            await _ensure_members_page(page, workspace, settings)
            if await _is_auth_required(page):
                raise _AuthFailedError("workspace redirected to auth page")

            member_count = await _extract_member_count(page)
            if member_count is not None and member_count >= workspace.max_users:
                raise _WorkspaceFullError(member_count)

            if await _contains_email(page, email):
                raise _DuplicateInviteError("Email is already present in workspace", member_count=member_count)

            await _click_first(page, INVITE_BUTTON_SELECTORS, settings.playwright_action_timeout_ms)
            await _wait_for_first(page, INVITE_DIALOG_SELECTORS, settings.playwright_action_timeout_ms)
            await _fill_first(page, INVITE_EMAIL_INPUT_SELECTORS, email, settings.playwright_action_timeout_ms)

            if await _has_duplicate_hint(page):
                raise _DuplicateInviteError("Email was already invited", member_count=member_count)

            await _click_first(page, INVITE_SUBMIT_SELECTORS, settings.playwright_action_timeout_ms)
            if not await _wait_for_success(page, settings.playwright_action_timeout_ms, email):
                raise _InviteFailedError("Invite success confirmation was not detected")
            return _result("invited", workspace, member_count=member_count)
        finally:
            logger.info("Playwright run finished for workspace %s", workspace.id)
            await context.close()


async def invite_to_workspace(
    workspace: ChatGPTWorkspaceConfig,
    email: str,
    settings: Settings,
) -> PlaywrightInviteResult:
    logger = get_logger("automation.playwright")
    attempts = max(1, settings.playwright_retry_attempts)
    last_error: str | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await _run_once(workspace, email, settings)
        except _DuplicateInviteError as exc:
            return _result("already_invited", workspace, member_count=exc.member_count, error_message=str(exc))
        except _WorkspaceFullError as exc:
            return _result("no_workspace_available", workspace, member_count=exc.member_count, error_message=str(exc))
        except _AuthFailedError as exc:
            return _result("auth_failed", workspace, error_message=str(exc))
        except _InviteFailedError as exc:
            return _result("invite_failed", workspace, error_message=str(exc))
        except _TransientInviteError as exc:
            last_error = str(exc)
            logger.warning(
                "Transient Playwright failure for workspace %s on attempt %s/%s: %s",
                workspace.id,
                attempt,
                attempts,
                exc,
            )
            if attempt >= attempts:
                return _result("invite_failed", workspace, error_message=last_error)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.exception("Unexpected Playwright error for workspace %s", workspace.id)
            return _result("unexpected_error", workspace, error_message=str(exc))
    return _result("invite_failed", workspace, error_message=last_error or "Unknown invite failure")
