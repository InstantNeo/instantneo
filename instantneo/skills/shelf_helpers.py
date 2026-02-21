# Backward compatibility stub - imports from navigation_helpers
from .navigation_helpers import (
    create_navigation_tools,
    create_navigation_tools as create_navigation_skills,
    NAVIGATION_PROMPT,
    NAVIGATION_PROMPT as SHELF_NAVIGATION_PROMPT,
)

__all__ = [
    'create_navigation_skills',
    'create_navigation_tools',
    'SHELF_NAVIGATION_PROMPT',
    'NAVIGATION_PROMPT',
]
