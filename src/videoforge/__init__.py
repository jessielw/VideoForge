"""VideoForge: rule-based encode and mux job queue; each group's rules live in a profile."""


def version() -> str:
    """The installed package's version ("unknown" when it isn't installed)."""
    try:
        from importlib.metadata import version as dist_version

        return dist_version("videoforge")
    except Exception:
        return "unknown"


def main() -> int:
    from videoforge.cli import main as cli_main

    return cli_main()
