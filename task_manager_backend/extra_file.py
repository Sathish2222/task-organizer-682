"""
Harmless extra module.

This file is intentionally unused by the application at runtime.
It exists to satisfy a request to add an additional file without changing
the backend behavior.
"""


# PUBLIC_INTERFACE
def get_placeholder_message() -> str:
    """Return a static placeholder message.

    This function is not imported by the application and has no side effects.
    """
    return "placeholder"
