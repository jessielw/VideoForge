"""VideoForge: rule-based encode and mux job queue; each group's rules live in a profile."""


def main() -> int:
    from videoforge.cli import main as cli_main

    return cli_main()
