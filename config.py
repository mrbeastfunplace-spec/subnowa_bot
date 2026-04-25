from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional during compile-only checks
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PLAYWRIGHT_PROFILE_DIR = "automation/auth_state/chrome_profile"
DEFAULT_PLAYWRIGHT_PROFILE_ROOT = "automation/auth_state/chrome_profiles"
DEFAULT_PLAYWRIGHT_DEBUG_DIR = "automation/debug/playwright"


def _load_env() -> None:
    env_path = BASE_DIR / ".env"
    if load_dotenv and env_path.exists():
        load_dotenv(env_path)


def _parse_admin_ids(value: str | None) -> list[int]:
    if not value:
        return []
    result: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        result.append(int(item))
    return result


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _coerce_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return _parse_bool(str(value), default)


def _coerce_int(value: object, default: int, *, field_name: str) -> int:
    if value in {None, ""}:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"ChatGPT workspace has invalid {field_name}: {value!r}") from exc
    return max(1, parsed)


@dataclass(slots=True, frozen=True)
class ChatGPTWorkspaceConfig:
    id: str
    name: str
    workspace_url: str
    profile_dir: Path | None = None
    storage_state_path: Path | None = None
    members_url: str | None = None
    max_users: int = 5
    enabled: bool = True
    source: str = "settings"
    db_id: int | None = None


def _resolve_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return BASE_DIR / path


def _default_playwright_profile_dir() -> Path:
    profile_dir_raw = os.getenv("PLAYWRIGHT_PROFILE_DIR", DEFAULT_PLAYWRIGHT_PROFILE_DIR).strip()
    return _resolve_path(profile_dir_raw or DEFAULT_PLAYWRIGHT_PROFILE_DIR)


def _default_playwright_profile_root() -> Path:
    configured = os.getenv("PLAYWRIGHT_PROFILE_ROOT", "").strip()
    if configured:
        return _resolve_path(configured)
    if _is_railway_runtime():
        return Path("/data/chrome_profiles")
    return BASE_DIR / "automation" / "auth_state" / "chrome_profiles"


def _is_railway_runtime() -> bool:
    return any(os.getenv(key) for key in ("RAILWAY_PROJECT_ID", "RAILWAY_ENVIRONMENT", "RAILWAY_SERVICE_ID"))


def _default_playwright_storage_state_dir() -> Path:
    configured = os.getenv("PLAYWRIGHT_STORAGE_STATE_DIR", "").strip()
    if configured:
        return _resolve_path(configured)
    if _is_railway_runtime():
        return Path("/data/auth_state")
    return BASE_DIR / "automation" / "auth_state" / "storage_states"


def _default_playwright_onboarding_profile_root() -> Path:
    configured = os.getenv("PLAYWRIGHT_ONBOARDING_PROFILE_DIR", "").strip()
    if configured:
        return _resolve_path(configured)
    if _is_railway_runtime():
        return Path("/data/auth_profiles")
    return BASE_DIR / "automation" / "auth_state" / "profiles"


def _default_playwright_debug_dir() -> Path:
    configured = os.getenv("PLAYWRIGHT_DEBUG_DIR", "").strip()
    if configured:
        return _resolve_path(configured)
    if _is_railway_runtime():
        return Path("/data/playwright_debug")
    return BASE_DIR / "automation" / "debug" / "playwright"


def _default_chatgpt_workspaces(
    *,
    default_profile_dir: Path,
    default_max_users: int,
) -> list[ChatGPTWorkspaceConfig]:
    return [
        ChatGPTWorkspaceConfig(
            id="main",
            name="main",
            workspace_url="https://chatgpt.com/",
            profile_dir=default_profile_dir,
            max_users=max(1, default_max_users),
            enabled=True,
            source="settings",
        )
    ]


def _parse_chatgpt_workspaces(
    value: str | None,
    *,
    default_profile_dir: Path,
    default_max_users: int,
) -> list[ChatGPTWorkspaceConfig]:
    if not value:
        return _default_chatgpt_workspaces(
            default_profile_dir=default_profile_dir,
            default_max_users=default_max_users,
        )
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError("CHATGPT_WORKSPACES_JSON must be a valid JSON array") from exc
    if not isinstance(payload, list):
        raise RuntimeError("CHATGPT_WORKSPACES_JSON must be a JSON array")
    if not payload:
        return _default_chatgpt_workspaces(
            default_profile_dir=default_profile_dir,
            default_max_users=default_max_users,
        )

    workspaces: list[ChatGPTWorkspaceConfig] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise RuntimeError("Each ChatGPT workspace config must be a JSON object")
        name = str(item.get("name") or f"workspace_{index}").strip()
        workspace_id = str(item.get("id") or name).strip() or f"workspace_{index}"
        workspace_url = str(item.get("workspace_url") or item.get("url") or "").strip()
        members_url = str(item.get("members_url") or "").strip() or None
        max_users = _coerce_int(item.get("max_users"), default_max_users, field_name="max_users")
        enabled = _coerce_bool(item.get("enabled", item.get("active")), True)
        if not workspace_url:
            raise RuntimeError(f"ChatGPT workspace '{workspace_id}' is missing workspace_url")
        workspaces.append(
            ChatGPTWorkspaceConfig(
                id=workspace_id,
                name=name,
                workspace_url=workspace_url,
                profile_dir=default_profile_dir,
                members_url=members_url,
                max_users=max_users,
                enabled=enabled,
                source="settings",
            )
        )
    return workspaces


@dataclass(slots=True)
class Settings:
    bot_token: str
    database_url: str
    admin_ids: list[int]
    support_url: str
    about_url: str
    review_url: str
    required_channel: str
    default_language: str = "ru"
    admin_language: str = "ru"
    trial_duration_days: int = 3
    payment_window_hours: int = 12
    chatgpt_workspaces: list[ChatGPTWorkspaceConfig] | None = None
    chatgpt_workspace_member_limit: int = 5
    playwright_profile_dir: Path = Path(DEFAULT_PLAYWRIGHT_PROFILE_DIR)
    playwright_profile_root: Path = Path(DEFAULT_PLAYWRIGHT_PROFILE_ROOT)
    playwright_headless: bool = True
    playwright_navigation_timeout_ms: int = 25000
    playwright_action_timeout_ms: int = 12000
    playwright_retry_attempts: int = 3
    playwright_storage_state_dir: Path = Path("automation/auth_state/storage_states")
    playwright_onboarding_profile_root: Path = Path("automation/auth_state/profiles")
    playwright_debug_dir: Path = Path(DEFAULT_PLAYWRIGHT_DEBUG_DIR)
    playwright_onboarding_timeout_sec: int = 1800

    @property
    def polling_lock_path(self) -> Path:
        return BASE_DIR / ".polling.lock"

    @property
    def automation_auth_state_dir(self) -> Path:
        return BASE_DIR / "automation" / "auth_state"


def load_settings() -> Settings:
    _load_env()

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    database_url = os.getenv("DATABASE_URL", "").strip()

    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    chatgpt_workspace_member_limit = int(os.getenv("CHATGPT_WORKSPACE_MEMBER_LIMIT", "5"))
    playwright_profile_dir = _default_playwright_profile_dir()
    playwright_profile_root = _default_playwright_profile_root()
    playwright_storage_state_dir = _default_playwright_storage_state_dir()
    playwright_onboarding_profile_root = _default_playwright_onboarding_profile_root()
    playwright_debug_dir = _default_playwright_debug_dir()

    return Settings(
        bot_token=bot_token,
        database_url=database_url,
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS")) or [7716923294],
        support_url=os.getenv("SUPPORT_URL", "https://t.me/subnowa_supportbot").strip(),
        about_url=os.getenv("ABOUT_URL", "https://subnowa.site").strip(),
        review_url=os.getenv("REVIEW_URL", "https://t.me/subbowaotzib").strip(),
        required_channel=os.getenv("REQUIRED_CHANNEL", "@UZB_TREND_MUCIQALAR_BASS_HIT").strip(),
        default_language=os.getenv("DEFAULT_LANGUAGE", "ru").strip() or "ru",
        admin_language="ru",
        trial_duration_days=int(os.getenv("TRIAL_DURATION_DAYS", "3")),
        payment_window_hours=int(os.getenv("PAYMENT_WINDOW_HOURS", "12")),
        chatgpt_workspaces=_parse_chatgpt_workspaces(
            os.getenv("CHATGPT_WORKSPACES_JSON"),
            default_profile_dir=playwright_profile_dir,
            default_max_users=chatgpt_workspace_member_limit,
        ),
        chatgpt_workspace_member_limit=chatgpt_workspace_member_limit,
        playwright_profile_dir=playwright_profile_dir,
        playwright_profile_root=playwright_profile_root,
        playwright_headless=_parse_bool(os.getenv("PLAYWRIGHT_HEADLESS"), True),
        playwright_navigation_timeout_ms=int(os.getenv("PLAYWRIGHT_NAVIGATION_TIMEOUT_MS", "25000")),
        playwright_action_timeout_ms=int(os.getenv("PLAYWRIGHT_ACTION_TIMEOUT_MS", "12000")),
        playwright_retry_attempts=int(os.getenv("PLAYWRIGHT_RETRY_ATTEMPTS", "3")),
        playwright_storage_state_dir=playwright_storage_state_dir,
        playwright_onboarding_profile_root=playwright_onboarding_profile_root,
        playwright_debug_dir=playwright_debug_dir,
        playwright_onboarding_timeout_sec=int(os.getenv("PLAYWRIGHT_ONBOARDING_TIMEOUT_SEC", "1800")),
    )
