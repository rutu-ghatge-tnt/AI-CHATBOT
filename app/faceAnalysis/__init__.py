"""
Face Analysis package (backend + frontend live directly under this folder).

``sys.path`` should include this directory; imports use ``backend.*`` and ``frontend.*``.
"""

__version__ = "2.0.0"

from .backend.core.config import settings

__all__ = ["settings"]
