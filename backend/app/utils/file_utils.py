import os
from collections.abc import Sequence
from pathlib import Path


def get_allowed_roots() -> list[Path] | None:
    """Get configured media roots for file browsing.

    Returns a list of Path objects representing allowed root directories.
    If no roots are configured, returns None (allowing unrestricted access).

    This is primarily for UI browsing organization, not strict security enforcement.
    In a desktop application, we trust the user's configured paths.
    """
    roots = os.environ.get("media")
    if roots:
        return [Path(p).resolve() for p in roots.split(";") if p]
    # For desktop app: If no roots configured, allow browsing from system roots
    # The file browser will show drive letters on Windows or root on Unix
    return


def is_under_allowed_roots(p: Path, roots: Sequence[Path] | None):
    """Check if a path is under allowed roots.

    If roots is None or empty, always returns True (permissive mode for desktop app).
    This provides a convenience check for file browser organization without
    being overly restrictive.
    """
    # no roots configured = trust everything
    if not roots:
        return True

    try:
        rp = p.resolve()
    except Exception:
        return False

    for r in roots:
        try:
            if r in rp.parents or rp == r:
                return True
        except Exception:
            continue
    return False
