from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
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
    "anti_bot_blocked",
    "unexpected_error",
]


PlaywrightWorkspaceValidationStatus = Literal[
    "active",
    "invalid_auth",
    "failed",
]


@dataclass(slots=True)
class PlaywrightInviteResult:
    status: PlaywrightResultStatus
    workspace_id: str | None = None
    workspace_name: str | None = None
    member_count: int | None = None
    error_message: str | None = None
    current_url: str | None = None
    page_title: str | None = None
    screenshot_path: str | None = None


@dataclass(slots=True)
class PlaywrightWorkspaceValidationResult:
    status: PlaywrightWorkspaceValidationStatus
    workspace_id: str | None = None
    workspace_name: str | None = None
    member_count: int | None = None
    workspace_url: str | None = None
    members_url: str | None = None
    error_message: str | None = None
    current_url: str | None = None
    page_title: str | None = None
    screenshot_path: str | None = None


@dataclass(slots=True)
class _PageDiagnostics:
    current_url: str
    title: str
    screenshot_path: str | None = None


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


class _AntiBotBlockedError(Exception):
    def __init__(self, diagnostics: _PageDiagnostics) -> None:
        super().__init__("Cloudflare anti-bot page detected")
        self.diagnostics = diagnostics


def _result(
    status: PlaywrightResultStatus,
    workspace: ChatGPTWorkspaceConfig,
    *,
    member_count: int | None = None,
    error_message: str | None = None,
    current_url: str | None = None,
    page_title: str | None = None,
    screenshot_path: str | None = None,
) -> PlaywrightInviteResult:
    return PlaywrightInviteResult(
        status=status,
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        member_count=member_count,
        error_message=error_message,
        current_url=current_url,
        page_title=page_title,
        screenshot_path=screenshot_path,
    )


def _validation_result(
    status: PlaywrightWorkspaceValidationStatus,
    workspace: ChatGPTWorkspaceConfig,
    *,
    workspace_name: str | None = None,
    member_count: int | None = None,
    workspace_url: str | None = None,
    members_url: str | None = None,
    error_message: str | None = None,
    current_url: str | None = None,
    page_title: str | None = None,
    screenshot_path: str | None = None,
) -> PlaywrightWorkspaceValidationResult:
    return PlaywrightWorkspaceValidationResult(
        status=status,
        workspace_id=workspace.id,
        workspace_name=workspace_name or workspace.name,
        member_count=member_count,
        workspace_url=workspace_url or workspace.workspace_url,
        members_url=members_url or workspace.members_url,
        error_message=error_message,
        current_url=current_url,
        page_title=page_title,
        screenshot_path=screenshot_path,
    )


def _diagnostics_summary(diagnostics: _PageDiagnostics) -> str:
    details = [
        f"Current URL: {diagnostics.current_url}.",
        f"Page title: {diagnostics.title}.",
    ]
    if diagnostics.screenshot_path:
        details.append(f"Screenshot: {diagnostics.screenshot_path}.")
    return " ".join(details)


async def _locator_text(locator) -> str:
    try:
        return (await locator.inner_text()).strip()
    except Exception:
        return ""


async def _wait_for_network_idle(page, *, delay_ms: int = 2500) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass
    await page.wait_for_timeout(delay_ms)


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


async def _wait_for_any(locators: tuple, timeout: int, *, error_message: str):
    last_error: Exception | None = None
    for locator in locators:
        try:
            await locator.wait_for(state="visible", timeout=timeout)
            return locator
        except Exception as exc:
            last_error = exc
    raise _TransientInviteError(error_message) from last_error


def _invite_entry_locators(page) -> tuple:
    return (
        page.get_by_role("button", name=re.compile(r"invite team members?", re.IGNORECASE)).first,
        page.get_by_role("link", name=re.compile(r"invite team members?", re.IGNORECASE)).first,
        page.get_by_role("button", name=re.compile(r"invite", re.IGNORECASE)).first,
        page.get_by_role("link", name=re.compile(r"invite", re.IGNORECASE)).first,
        page.locator("text=Invite team members").first,
        page.locator("text=Invite").first,
        *(page.locator(selector).first for selector in INVITE_BUTTON_SELECTORS),
        *(page.locator(selector).first for selector in MEMBERS_NAV_SELECTORS),
    )


def _invite_dialog_locators(page) -> tuple:
    return tuple(page.locator(selector).first for selector in INVITE_DIALOG_SELECTORS)


def _invite_email_input_locators(root) -> tuple:
    return (
        root.get_by_role("textbox", name=re.compile(r"email", re.IGNORECASE)).first,
        root.locator('input[type="email"]').first,
        root.locator('input[placeholder*="email" i]').first,
        root.locator('input[aria-label*="email" i]').first,
        root.locator('input[name*="email" i]').first,
        root.locator("textarea").first,
        *(root.locator(selector).first for selector in INVITE_EMAIL_INPUT_SELECTORS),
    )


def _invite_submit_locators(root) -> tuple:
    return (
        root.get_by_role("button", name=re.compile(r"invite|send|add", re.IGNORECASE)).first,
        *(root.locator(selector).first for selector in INVITE_SUBMIT_SELECTORS),
    )


async def _resolve_invite_root(page, timeout: int):
    try:
        return await _wait_for_any(
            _invite_dialog_locators(page),
            min(timeout, 4_000),
            error_message="Invite panel was not detected",
        )
    except _TransientInviteError:
        return page.locator("body").first


async def _capture_page_diagnostics(
    page,
    workspace: ChatGPTWorkspaceConfig,
    settings: Settings,
    logger,
    *,
    label: str,
) -> _PageDiagnostics:
    current_url = page.url or "-"
    try:
        title = (await page.title()).strip() or "-"
    except Exception:
        title = "-"

    settings.playwright_debug_dir.mkdir(parents=True, exist_ok=True)
    safe_workspace = re.sub(r"[^a-zA-Z0-9_.-]+", "_", workspace.id or "workspace")
    safe_label = re.sub(r"[^a-zA-Z0-9_.-]+", "_", label)
    screenshot_path = settings.playwright_debug_dir / f"{safe_workspace}_{safe_label}_{int(time.time() * 1000)}.png"
    screenshot_saved = False
    try:
        await page.screenshot(path=str(screenshot_path), full_page=True)
        screenshot_saved = True
    except Exception as exc:
        logger.warning(
            "Failed to capture Playwright screenshot | workspace=%s label=%s error=%s",
            workspace.id,
            label,
            exc,
        )

    final_path = str(screenshot_path) if screenshot_saved else None
    logger.error(
        "Playwright diagnostics | workspace=%s label=%s url=%s title=%s screenshot=%s",
        workspace.id,
        label,
        current_url,
        title,
        final_path or "not-saved",
    )
    return _PageDiagnostics(
        current_url=current_url,
        title=title,
        screenshot_path=final_path,
    )


async def _raise_if_anti_bot_blocked(
    page,
    workspace: ChatGPTWorkspaceConfig,
    settings: Settings,
    logger,
    *,
    label: str,
) -> None:
    try:
        title = (await page.title()).strip()
    except Exception:
        return
    if title.lower() != "just a moment...":
        return
    diagnostics = await _capture_page_diagnostics(page, workspace, settings, logger, label=label)
    raise _AntiBotBlockedError(diagnostics)


async def _open_invite_panel(
    page,
    settings: Settings,
    workspace: ChatGPTWorkspaceConfig,
    logger,
    *,
    label: str,
) -> None:
    timeout = settings.playwright_action_timeout_ms
    last_error: Exception | None = None
    for attempt in range(1, 3):
        await _wait_for_network_idle(page)
        await _raise_if_anti_bot_blocked(page, workspace, settings, logger, label=f"{label}_ready_{attempt}")
        try:
            root = await _resolve_invite_root(page, timeout)
            await _wait_for_any(
                _invite_email_input_locators(root),
                min(timeout, 3_000),
                error_message="Invite email input was not found",
            )
            return
        except _TransientInviteError:
            pass

        try:
            invite_button = await _wait_for_any(
                _invite_entry_locators(page),
                min(timeout, 4_000),
                error_message="Invite team members button was not found in the workspace sidebar",
            )
            await invite_button.click(timeout=timeout)
            await _wait_for_network_idle(page, delay_ms=2_000)
            await _raise_if_anti_bot_blocked(page, workspace, settings, logger, label=f"{label}_opened_{attempt}")
            root = await _resolve_invite_root(page, timeout)
            await _wait_for_any(
                _invite_email_input_locators(root),
                min(timeout, 4_000),
                error_message="Invite email input was not found after opening the invite panel",
            )
            return
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                await page.wait_for_timeout(2_500)

    raise _TransientInviteError("Invite team members button was not found after retries") from last_error


async def _fill_invite_email(page, email: str, timeout: int) -> None:
    root = await _resolve_invite_root(page, timeout)
    locator = await _wait_for_any(
        _invite_email_input_locators(root),
        timeout,
        error_message="Invite email input was not found",
    )
    try:
        await locator.fill(email, timeout=timeout)
    except Exception as exc:
        raise _TransientInviteError("Failed to fill invite email") from exc


async def _submit_invite(page, timeout: int) -> None:
    root = await _resolve_invite_root(page, timeout)
    locator = await _wait_for_any(
        _invite_submit_locators(root),
        timeout,
        error_message="Invite submit button was not found",
    )
    try:
        await locator.click(timeout=timeout)
    except Exception as exc:
        raise _TransientInviteError("Failed to submit invite") from exc


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


async def _ensure_invite_flow_ready(
    page,
    settings: Settings,
    workspace: ChatGPTWorkspaceConfig,
    logger,
    *,
    label: str,
) -> None:
    await _wait_for_network_idle(page)
    await _raise_if_anti_bot_blocked(page, workspace, settings, logger, label=f"{label}_before_invite")
    await _open_invite_panel(page, settings, workspace, logger, label=label)
    await _raise_if_anti_bot_blocked(page, workspace, settings, logger, label=f"{label}_after_invite")


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
        await _wait_for_network_idle(page, delay_ms=1500)
    except Exception:
        return False
    return await _contains_email(page, email)


def _workspace_auth_artifact_exists(workspace: ChatGPTWorkspaceConfig) -> bool:
    if workspace.profile_dir is None:
        return False
    return workspace.profile_dir.exists() and workspace.profile_dir.is_dir()


async def _open_workspace_context(playwright, workspace: ChatGPTWorkspaceConfig, settings: Settings, *, headless: bool):
    if workspace.profile_dir is None:
        raise _TransientInviteError("Workspace does not have a profile_dir configured")

    args = ["--disable-blink-features=AutomationControlled"]
    context = await playwright.chromium.launch_persistent_context(
        str(workspace.profile_dir),
        headless=headless,
        args=args,
    )
    context.set_default_timeout(settings.playwright_action_timeout_ms)
    context.set_default_navigation_timeout(settings.playwright_navigation_timeout_ms)
    return context, None


async def _close_workspace_context(context, browser) -> None:
    await context.close()
    if browser is not None:
        await browser.close()


async def _workspace_page(context):
    for page in context.pages:
        if (page.url or "").strip() not in {"", "about:blank"}:
            return page
    return context.pages[0] if context.pages else await context.new_page()


def _derive_workspace_url(members_url: str | None, fallback: str) -> str:
    if members_url and "/members" in members_url:
        return members_url.split("/members", 1)[0]
    if members_url:
        return members_url
    return fallback


def _normalize_url(url: str | None) -> str:
    return (url or "").strip().rstrip("/")


def _is_workspace_url(url: str | None) -> bool:
    lower = _normalize_url(url).lower()
    return "/admin/" in lower or lower.endswith("/admin") or "/members" in lower


def _target_workspace_url(workspace: ChatGPTWorkspaceConfig) -> str:
    return workspace.members_url or workspace.workspace_url


def _page_matches_workspace(page_url: str | None, workspace: ChatGPTWorkspaceConfig) -> bool:
    current_url = _normalize_url(page_url)
    target_url = _normalize_url(_target_workspace_url(workspace))
    if current_url and target_url:
        if current_url == target_url or current_url.startswith(target_url + "/"):
            return True
    if _is_workspace_url(current_url) and not _is_workspace_url(target_url):
        return True
    return False


async def _ensure_workspace_page_ready(
    page,
    workspace: ChatGPTWorkspaceConfig,
    settings: Settings,
    logger,
    *,
    label: str,
) -> None:
    await _wait_for_network_idle(page, delay_ms=1000)
    await _raise_if_anti_bot_blocked(page, workspace, settings, logger, label=f"{label}_existing_page")
    if _page_matches_workspace(page.url, workspace):
        return

    target_url = _target_workspace_url(workspace)
    if not target_url or not target_url.startswith("http"):
        raise _TransientInviteError("Workspace URL is not configured")

    try:
        await page.goto(target_url, wait_until="domcontentloaded")
        await _wait_for_network_idle(page)
    except Exception as exc:
        raise _TransientInviteError("Workspace page did not load") from exc
    await _raise_if_anti_bot_blocked(page, workspace, settings, logger, label=f"{label}_after_goto")


async def _extract_workspace_name(page, workspace: ChatGPTWorkspaceConfig) -> str:
    for selector in ("h1", "main h1", "header h1"):
        try:
            text = (await page.locator(selector).first.inner_text(timeout=700)).strip()
        except Exception:
            continue
        if text:
            return text
    try:
        title = (await page.title()).strip()
    except Exception:
        title = ""
    if title:
        return title.replace(" - ChatGPT", "").strip() or workspace.name
    return workspace.name


async def _run_once(workspace: ChatGPTWorkspaceConfig, email: str, settings: Settings) -> PlaywrightInviteResult:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - depends on local install
        return _result("unexpected_error", workspace, error_message=f"Playwright is not installed: {exc}")

    logger = get_logger("automation.playwright")
    logger.info(
        "Using Playwright workspace profile | workspace=%s profile_dir=%s members_url=%s workspace_url=%s",
        workspace.id,
        workspace.profile_dir,
        workspace.members_url,
        workspace.workspace_url,
    )
    if not _workspace_auth_artifact_exists(workspace):
        return _result(
            "profile_not_found",
            workspace,
            error_message=f"Workspace profile dir was not found: profile_dir={workspace.profile_dir}",
        )

    async with async_playwright() as playwright:
        logger.info(
            "Launching Playwright workspace context | workspace=%s profile_dir=%s members_url=%s workspace_url=%s",
            workspace.id,
            workspace.profile_dir,
            workspace.members_url,
            workspace.workspace_url,
        )
        context, browser = await _open_workspace_context(
            playwright,
            workspace,
            settings,
            headless=settings.playwright_headless,
        )
        page = await _workspace_page(context)
        try:
            await _ensure_workspace_page_ready(page, workspace, settings, logger, label="invite_open")
            if await _is_auth_required(page):
                raise _AuthFailedError("Persistent profile is no longer authenticated")

            await _ensure_invite_flow_ready(page, settings, workspace, logger, label="invite_panel")
            if await _is_auth_required(page):
                raise _AuthFailedError("Workspace redirected to auth page")

            member_count = await _extract_member_count(page)
            if member_count is not None and member_count >= workspace.max_users:
                raise _WorkspaceFullError(member_count)

            if await _contains_email(page, email):
                raise _DuplicateInviteError("Email is already present in workspace", member_count=member_count)

            await _fill_invite_email(page, email, settings.playwright_action_timeout_ms)
            if await _has_duplicate_hint(page):
                raise _DuplicateInviteError("Email was already invited", member_count=member_count)

            await _submit_invite(page, settings.playwright_action_timeout_ms)
            await _raise_if_anti_bot_blocked(page, workspace, settings, logger, label="invite_after_submit")
            if not await _wait_for_success(page, settings.playwright_action_timeout_ms, email):
                raise _InviteFailedError("Invite success confirmation was not detected")
            return _result("invited", workspace, member_count=member_count)
        except (_DuplicateInviteError, _WorkspaceFullError):
            raise
        except _AuthFailedError as exc:
            diagnostics = await _capture_page_diagnostics(page, workspace, settings, logger, label="auth_failed")
            raise _AuthFailedError(f"{exc}. {_diagnostics_summary(diagnostics)}") from exc
        except _InviteFailedError as exc:
            diagnostics = await _capture_page_diagnostics(page, workspace, settings, logger, label="invite_failed")
            raise _InviteFailedError(f"{exc}. {_diagnostics_summary(diagnostics)}") from exc
        except _TransientInviteError as exc:
            diagnostics = await _capture_page_diagnostics(page, workspace, settings, logger, label="invite_transient")
            raise _TransientInviteError(f"{exc}. {_diagnostics_summary(diagnostics)}") from exc
        except _AntiBotBlockedError:
            raise
        except Exception as exc:
            diagnostics = await _capture_page_diagnostics(page, workspace, settings, logger, label="invite_unexpected")
            raise _InviteFailedError(
                f"Failed to send invite in the ChatGPT Business workspace. {_diagnostics_summary(diagnostics)}"
            ) from exc
        finally:
            logger.info("Playwright run finished for workspace %s", workspace.id)
            await _close_workspace_context(context, browser)


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
        except _AntiBotBlockedError as exc:
            return _result(
                "anti_bot_blocked",
                workspace,
                error_message=f"anti_bot_blocked. {_diagnostics_summary(exc.diagnostics)}",
                current_url=exc.diagnostics.current_url,
                page_title=exc.diagnostics.title,
                screenshot_path=exc.diagnostics.screenshot_path,
            )
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


async def validate_workspace_auth(
    workspace: ChatGPTWorkspaceConfig,
    settings: Settings,
    *,
    headless: bool | None = None,
) -> PlaywrightWorkspaceValidationResult:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - depends on local install
        return _validation_result("failed", workspace, error_message=f"Playwright is not installed: {exc}")

    if not _workspace_auth_artifact_exists(workspace):
        return _validation_result(
            "invalid_auth",
            workspace,
            error_message=f"Workspace profile dir was not found: profile_dir={workspace.profile_dir}",
        )

    logger = get_logger("automation.playwright")
    chosen_headless = settings.playwright_headless if headless is None else headless

    async with async_playwright() as playwright:
        context = None
        browser = None
        page = None
        try:
            context, browser = await _open_workspace_context(
                playwright,
                workspace,
                settings,
                headless=chosen_headless,
            )
            page = await _workspace_page(context)
            await _ensure_workspace_page_ready(page, workspace, settings, logger, label="validation_open")
            if await _is_auth_required(page):
                raise _AuthFailedError("Workspace requires a fresh login")

            await _ensure_invite_flow_ready(page, settings, workspace, logger, label="validation_invite")
            if await _is_auth_required(page):
                raise _AuthFailedError("Invite area redirected to auth page")

            member_count = await _extract_member_count(page)
            members_url = page.url or workspace.members_url or workspace.workspace_url
            workspace_url = _derive_workspace_url(members_url, workspace.workspace_url)
            workspace_name = await _extract_workspace_name(page, workspace)
            return _validation_result(
                "active",
                workspace,
                workspace_name=workspace_name,
                member_count=member_count,
                workspace_url=workspace_url,
                members_url=members_url,
            )
        except _AuthFailedError as exc:
            if context is not None and page is not None:
                diagnostics = await _capture_page_diagnostics(page, workspace, settings, logger, label="validation_auth_failed")
                return _validation_result(
                    "invalid_auth",
                    workspace,
                    error_message=f"{exc}. {_diagnostics_summary(diagnostics)}",
                    current_url=diagnostics.current_url,
                    page_title=diagnostics.title,
                    screenshot_path=diagnostics.screenshot_path,
                )
            return _validation_result("invalid_auth", workspace, error_message=str(exc))
        except _AntiBotBlockedError as exc:
            return _validation_result(
                "failed",
                workspace,
                error_message=f"anti_bot_blocked. {_diagnostics_summary(exc.diagnostics)}",
                current_url=exc.diagnostics.current_url,
                page_title=exc.diagnostics.title,
                screenshot_path=exc.diagnostics.screenshot_path,
            )
        except Exception as exc:  # pragma: no cover - defensive fallback
            if context is not None and page is not None:
                diagnostics = await _capture_page_diagnostics(page, workspace, settings, logger, label="validation_failed")
                logger.exception("Workspace validation failed for %s", workspace.id)
                return _validation_result(
                    "failed",
                    workspace,
                    error_message=f"{exc}. {_diagnostics_summary(diagnostics)}",
                    current_url=diagnostics.current_url,
                    page_title=diagnostics.title,
                    screenshot_path=diagnostics.screenshot_path,
                )
            logger.exception("Workspace validation failed for %s", workspace.id)
            return _validation_result("failed", workspace, error_message=str(exc))
        finally:
            if context is not None:
                await _close_workspace_context(context, browser)
