"""
Guard Admin API module.
Owner: SEC-2 (Authority-side Security)
"""

from .routes import router as admin_router

__all__ = ["admin_router"]
