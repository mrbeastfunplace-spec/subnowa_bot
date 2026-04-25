from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import ChatGPTWorkspaceConfig, Settings
from db.base import ChatGPTWorkspaceStatus, utcnow
from db.models import ChatGPTWorkspace


_WORKSPACE_ID_PATTERN = re.compile(r"^workspace_(\d+)$")


def ensure_workspace_directories(settings: Settings) -> None:
    settings.playwright_profile_root.mkdir(parents=True, exist_ok=True)
    settings.playwright_storage_state_dir.mkdir(parents=True, exist_ok=True)
    settings.playwright_onboarding_profile_root.mkdir(parents=True, exist_ok=True)


def profile_dir(settings: Settings, workspace_id: str) -> Path:
    ensure_workspace_directories(settings)
    return settings.playwright_profile_root / workspace_id


def storage_state_path(settings: Settings, workspace_id: str) -> Path:
    ensure_workspace_directories(settings)
    return settings.playwright_storage_state_dir / f"{workspace_id}.json"


def onboarding_profile_dir(settings: Settings, workspace_id: str) -> Path:
    ensure_workspace_directories(settings)
    return settings.playwright_onboarding_profile_root / workspace_id


def short_storage_reference(path: str | Path | None) -> str:
    if not path:
        return "-"
    return Path(path).name


def workspace_profile_path(workspace: ChatGPTWorkspace) -> Path | None:
    profile_dir_value = (workspace.profile_dir or "").strip()
    if not profile_dir_value:
        return None
    return Path(profile_dir_value)


def workspace_profile_ready(path: Path | None) -> bool:
    if path is None or not path.exists() or not path.is_dir():
        return False
    try:
        next(path.iterdir())
    except StopIteration:
        return False
    except OSError:
        return False
    return True


def workspace_status_label(status: ChatGPTWorkspaceStatus) -> str:
    return {
        ChatGPTWorkspaceStatus.PENDING_SETUP: "pending_setup",
        ChatGPTWorkspaceStatus.ACTIVE: "active",
        ChatGPTWorkspaceStatus.INVALID_AUTH: "invalid_auth",
        ChatGPTWorkspaceStatus.DISABLED: "disabled",
    }[status]


async def list_registry_workspaces(session: AsyncSession) -> list[ChatGPTWorkspace]:
    result = await session.scalars(
        select(ChatGPTWorkspace).order_by(ChatGPTWorkspace.created_at.desc(), ChatGPTWorkspace.id.desc())
    )
    return list(result.all())


async def get_workspace(session: AsyncSession, workspace_db_id: int) -> ChatGPTWorkspace | None:
    return await session.scalar(select(ChatGPTWorkspace).where(ChatGPTWorkspace.id == workspace_db_id))


async def get_workspace_by_code(session: AsyncSession, workspace_id: str) -> ChatGPTWorkspace | None:
    return await session.scalar(select(ChatGPTWorkspace).where(ChatGPTWorkspace.workspace_id == workspace_id))


async def generate_workspace_id(session: AsyncSession) -> str:
    existing_ids = await session.scalars(select(ChatGPTWorkspace.workspace_id))
    max_index = 0
    for workspace_id in existing_ids:
        match = _WORKSPACE_ID_PATTERN.fullmatch(workspace_id or "")
        if match:
            max_index = max(max_index, int(match.group(1)))
    return f"workspace_{max_index + 1}"


async def create_pending_workspace(
    session: AsyncSession,
    *,
    settings: Settings,
    created_by_admin_telegram_id: int,
    workspace_id: str | None = None,
) -> ChatGPTWorkspace:
    code = workspace_id or await generate_workspace_id(session)
    record = ChatGPTWorkspace(
        workspace_id=code,
        workspace_name=code,
        workspace_url="https://chatgpt.com/admin",
        profile_dir=str(profile_dir(settings, code)),
        storage_state_path="",
        temp_profile_dir=None,
        status=ChatGPTWorkspaceStatus.PENDING_SETUP,
        max_users=max(1, settings.chatgpt_workspace_member_limit),
        created_by_admin_telegram_id=created_by_admin_telegram_id,
        last_error=None,
    )
    session.add(record)
    await session.flush()
    return record


def as_config(workspace: ChatGPTWorkspace) -> ChatGPTWorkspaceConfig:
    return ChatGPTWorkspaceConfig(
        id=workspace.workspace_id,
        name=workspace.workspace_name or workspace.workspace_id,
        workspace_url=workspace.workspace_url,
        profile_dir=workspace_profile_path(workspace),
        storage_state_path=None,
        members_url=workspace.members_url,
        max_users=max(1, workspace.max_users or 1),
        enabled=workspace.status == ChatGPTWorkspaceStatus.ACTIVE,
        source="registry",
        db_id=workspace.id,
    )


async def list_active_workspace_configs(
    session: AsyncSession,
    settings: Settings,
) -> list[ChatGPTWorkspaceConfig]:
    configs: list[ChatGPTWorkspaceConfig] = []

    registry_workspaces = await session.scalars(
        select(ChatGPTWorkspace).where(ChatGPTWorkspace.status == ChatGPTWorkspaceStatus.ACTIVE)
    )
    for workspace in registry_workspaces:
        config = as_config(workspace)
        if config.profile_dir is None:
            continue
        configs.append(config)
    return configs


async def mark_workspace_result(
    session: AsyncSession,
    workspace: ChatGPTWorkspace,
    *,
    status: ChatGPTWorkspaceStatus,
    workspace_name: str | None = None,
    workspace_url_value: str | None = None,
    members_url: str | None = None,
    current_users_count: int | None = None,
    error_message: str | None = None,
) -> ChatGPTWorkspace:
    workspace.status = status
    workspace.last_checked_at = utcnow()
    workspace.last_error = error_message
    workspace.updated_at = utcnow()
    if workspace_name:
        workspace.workspace_name = workspace_name
    if workspace_url_value:
        workspace.workspace_url = workspace_url_value
    if members_url:
        workspace.members_url = members_url
    if current_users_count is not None:
        workspace.current_users_count = current_users_count
    await session.flush()
    return workspace


async def set_workspace_enabled(
    session: AsyncSession,
    workspace: ChatGPTWorkspace,
    *,
    enabled: bool,
) -> ChatGPTWorkspace:
    if enabled:
        path = workspace_profile_path(workspace)
        workspace.status = (
            ChatGPTWorkspaceStatus.ACTIVE if workspace_profile_ready(path) else ChatGPTWorkspaceStatus.INVALID_AUTH
        )
    else:
        workspace.status = ChatGPTWorkspaceStatus.DISABLED
    workspace.updated_at = utcnow()
    await session.flush()
    return workspace
