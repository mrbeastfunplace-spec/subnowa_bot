from handlers.legacy_catalog import build_catalog_router
from handlers.profile import build_profile_router
from handlers.start import build_start_router

__all__ = [
    "build_catalog_router",
    "build_profile_router",
    "build_start_router",
]
