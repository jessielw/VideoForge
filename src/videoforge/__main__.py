"""`python -m videoforge`: the same as the `videoforge` command (the portable build's launcher runs this)."""

from videoforge import main

if __name__ == "__main__":
    raise SystemExit(main())
