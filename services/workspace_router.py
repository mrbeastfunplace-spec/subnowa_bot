from __future__ import annotations

from config import ChatGPTWorkspaceConfig


class WorkspaceRouter:
    def __init__(self, workspaces: list[ChatGPTWorkspaceConfig] | None) -> None:
        self._workspaces = list(workspaces or [])

    def has_workspaces(self) -> bool:
        return any(workspace.enabled for workspace in self._workspaces)

    def iter_workspaces(self, excluded_ids: set[str] | None = None) -> list[ChatGPTWorkspaceConfig]:
        excluded = excluded_ids or set()
        return [
            workspace
            for workspace in self._workspaces
            if workspace.enabled and workspace.id not in excluded
        ]
