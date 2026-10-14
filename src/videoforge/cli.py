"""Command line entry point: videoforge serve | validate | plan | run."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from videoforge.core.config import load_app_config
from videoforge.core.models import Issue, Plan, Severity, SourceInfo
from videoforge.core.profile import Profile
from videoforge.profiles import default_profile_id, get_profile

console = Console()

_SEV_STYLE = {Severity.BLOCK: "bold red", Severity.WARN: "yellow", Severity.INFO: "dim"}


def _print_issues(issues: list[Issue], min_sev: Severity = Severity.INFO) -> None:
    order = [Severity.INFO, Severity.WARN, Severity.BLOCK]
    for i in issues:
        if order.index(i.severity) >= order.index(min_sev):
            console.print(f"  [{_SEV_STYLE[i.severity]}]{i.severity.value:>5}[/] {i.code}: {escape(i.message)}", highlight=False)


def report_validation(profile: Profile, targets: list[tuple[str, SourceInfo]], min_sev: Severity, summary: bool) -> int:
    """Check each release with the profile's release checks and print the results; 1 if any is blocked."""
    codes: Counter[str] = Counter()
    failed = 0
    for name, info in targets:
        issues = profile.validate_release(info)
        shown = [i for i in issues if i.severity is Severity.BLOCK or (min_sev is not Severity.BLOCK and i.severity is Severity.WARN)]
        codes.update(i.code for i in issues if i.severity is not Severity.INFO)
        if any(i.severity is Severity.BLOCK for i in issues):
            failed += 1
        if not summary and shown:
            console.print(f"[bold]{escape(name)}[/]")
            _print_issues(shown, min_sev)

    console.print(f"\n{len(targets) - failed}/{len(targets)} pass (no blocking issues)")
    if codes:
        table = Table("issue", "count")
        for code, n in codes.most_common():
            table.add_row(code, str(n))
        console.print(table)
    return 1 if failed else 0


def cmd_validate(args: argparse.Namespace) -> int:
    from videoforge.core.mediainfo_text import parse_mediainfo_text
    from videoforge.core.probe import probe

    app = load_app_config()
    profile = get_profile(args.profile or default_profile_id(app.profile))
    targets: list[tuple[str, SourceInfo]] = []
    for path in args.paths:
        if path.suffix == ".txt":
            targets.append((path.name, parse_mediainfo_text(path.read_text(encoding="utf-8"), name=path.stem)))
        else:
            targets.append((path.name, probe(path, app.tools.mkvmerge)))
    return report_validation(profile, targets, Severity(args.min_severity), args.summary)


_FLAG_NAMES = (("default", "default"), ("forced", "forced"), ("hearing_impaired", "sdh"), ("commentary", "commentary"),
               ("original", "original"), ("visual_impaired", "AD"))


def _flags(track) -> str:
    return ", ".join(name for key, name in _FLAG_NAMES if getattr(track, key))


def print_plan(plan: Plan) -> None:
    status = {Severity.BLOCK: "[bold red]BLOCKED[/]", Severity.WARN: "[yellow]WARN[/]", None: "[green]READY[/]"}[plan.status]
    console.print(f"\n[bold]{escape(plan.source.name)}[/]  {status}  {plan.resolution}  orig={plan.original_language}")
    table = Table("#", "type", "action", "title", "lang", "flags", "from", show_lines=False)
    for i, a in enumerate(plan.audio, 1):
        src = a.source
        action = a.action.value + (f" {a.bitrate_kbps}k" if a.bitrate_kbps else "") + (" +upmix" if a.upmix_50 else "")
        table.add_row(str(i), "audio", action, a.title, a.language, _flags(a),
                      escape(f"#{src.index + 1} {src.format_name} {src.layout} {src.title}"))
    for i, s in enumerate(plan.subs, 1):
        src = s.source
        where = src.external_path.name if src.external_path else f"#{src.index + 1} {src.format.value} {src.title}"
        table.add_row(str(i), "sub", s.slot or src.format.value, s.title, s.language, _flags(s), escape(where))
    console.print(table)
    _print_issues(plan.issues)


def cmd_plan(args: argparse.Namespace) -> int:
    from videoforge.core.jobs import discover_jobs, plan_job, probe_inputs

    app = load_app_config()
    profile = get_profile(args.profile or default_profile_id(app.profile))
    found = discover_jobs(args.paths, app)
    for e in found.unmatched.encodes:
        console.print(f"[yellow]Unmatched encode:[/] {escape(e.name)}")
    for e in found.unmatched.subtitles + found.unmatched.chapters:
        console.print(f"[yellow]Unmatched file:[/] {escape(e.name)}")
    blocked = shown = 0
    plans: list[Plan] = []
    for job in found.jobs:
        if args.only and not any(o in job.source.name for o in args.only):
            continue
        plan = plan_job(profile, probe_inputs(job, app), original_language=args.orig_lang)
        plans.append(plan)
        print_plan(plan)
        if job.subtitles:
            console.print("  [dim]external: " + escape(", ".join(p.name for p in job.subtitles)) + "[/]", highlight=False)
        if plan.chapters_path:
            console.print(f"  [dim]chapters: {escape(str(plan.chapters_path))}[/]", highlight=False)
        blocked += plan.blocked
        shown += 1
    console.print(f"\n{shown - blocked}/{shown} ready")
    if args.out:
        from videoforge.core.plan_io import dump_plans

        dump_plans(plans, args.out)
        console.print(f"Wrote {len(plans)} plan(s) to {escape(str(args.out))}")
    return 1 if blocked else 0


_STATUS_STYLE = {
    "done": "[green]DONE[/]",
    "invalid": "[bold red]INVALID[/]",
    "failed": "[bold red]FAILED[/]",
    "skipped": "[yellow]SKIPPED[/]",
    "cancelled": "[yellow]CANCELLED[/]",
}


def cmd_run(args: argparse.Namespace) -> int:
    from videoforge.core.execute.process import CancelToken
    from videoforge.core.job import JobStatus
    from videoforge.core.pipeline.run import run_plan
    from videoforge.core.plan_io import load_plans

    app = load_app_config()
    plans = load_plans(args.plan)
    if args.only:
        plans = [p for p in plans if any(o in p.source.name for o in args.only)]
    cancel = CancelToken()

    def log(line: str) -> None:
        if args.verbose:
            console.print(f"    [dim]{escape(line)}[/]", highlight=False)

    def progress(p) -> None:
        if p.fraction == 0.0 or p.reused:
            console.print(f"  [{p.index + 1}/{p.total}] {escape(p.step.label)}", highlight=False)

    results = []
    for n, plan in enumerate(plans, 1):
        console.print(f"\n[bold]({n}/{len(plans)}) {escape(plan.source.name)}[/]")
        try:
            result = run_plan(
                plan, args.out_dir, get_profile(plan.profile or default_profile_id(app.profile)), app,
                progress=progress, log=log, cancel=cancel,
            )
        except KeyboardInterrupt:
            console.print("[yellow]Interrupted[/]")
            return 130
        results.append(result)
        console.print(f"  {_STATUS_STYLE[result.status]} {escape(str(result.output or ''))}", highlight=False)
        if result.error:
            console.print(f"  {escape(result.error)}", highlight=False)
        _print_issues(result.issues, Severity.WARN)

    counts = Counter(r.status for r in results)
    console.print("\n" + ", ".join(f"{counts[s]} {s.value}" for s in JobStatus if counts[s]))
    return 0 if all(r.status is JobStatus.DONE for r in results) else 1


def _bring_up_running(url: str, open_browser: bool) -> bool:
    """When VideoForge already answers at `url`, show its window (or open the browser) instead of starting again."""
    import json
    import urllib.request
    import webbrowser

    try:
        with urllib.request.urlopen(url + "/api/health", timeout=1) as r:
            if not json.load(r).get("ok"):
                return False
    except (OSError, ValueError):
        return False
    try:
        urllib.request.urlopen(urllib.request.Request(url + "/api/window/show", data=b"", method="POST"), timeout=5)
        console.print("VideoForge is already running: its window is up")
    except OSError:  # it runs in the browser
        console.print(f"VideoForge is already running on [bold]{url}[/]")
        if open_browser:
            webbrowser.open(url)
    return True


def cmd_serve(args: argparse.Namespace) -> int:
    import threading
    import webbrowser

    import uvicorn

    from videoforge.server.app import create_app
    from videoforge.server.settings import ServerSettings

    settings = ServerSettings(host=args.host, port=args.port)
    if args.data_dir:
        settings.data_dir = args.data_dir
    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '::') else args.host}:{args.port}"
    if _bring_up_running(url, open_browser=args.window or not args.no_browser):
        return 0
    if args.window:
        from videoforge.desktop import run_window

        console.print(f"VideoForge on [bold]{url}[/], in its own window (closing it keeps VideoForge in the tray;"
                      " Quit there or Ctrl+C here to stop)")
        return run_window(create_app(settings), args.host, args.port, url, settings.data_dir)
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, (url,)).start()
    console.print(f"VideoForge on [bold]{url}[/] (Ctrl+C to stop)")
    uvicorn.run(create_app(settings), host=args.host, port=args.port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="videoforge", description="VideoForge: encode and mux job queue (`videoforge serve` for the web app)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="check finished releases with a profile's checks (MKV or MediaInfo .txt)")
    p.add_argument("paths", nargs="+", type=Path)
    p.add_argument("--summary", action="store_true", help="only print issue counts")
    p.add_argument("--min-severity", choices=["warn", "block"], default="warn")
    p.add_argument("--profile", help="rules to check against (default: videoforge.toml `profile`)")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("plan", help="pair sources with encodes and show what would be muxed")
    p.add_argument("paths", nargs="+", type=Path, help="MKV files or folders")
    p.add_argument("--orig-lang", help="original language for the batch (e.g. en, ja)")
    p.add_argument("--profile", help="rules to plan with (default: videoforge.toml `profile`)")
    p.add_argument("--only", nargs="*", help="only print plans whose source name contains one of these")
    p.add_argument("--out", type=Path, help="write the plans to this plan.json for `videoforge run`")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("run", help="encode and mux the plans in a plan.json, then validate each output")
    p.add_argument("plan", type=Path, help="plan.json from `videoforge plan --out`")
    p.add_argument("--out-dir", type=Path, required=True, help="folder for the muxed releases")
    p.add_argument("--only", nargs="*", help="only run plans whose source name contains one of these")
    p.add_argument("-v", "--verbose", action="store_true", help="show tool output")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("serve", help="start the web app (http://127.0.0.1:8765) and open it in the browser")
    p.add_argument("--host", default="127.0.0.1", help="interface to listen on (default: this machine only)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true", help="don't open the browser")
    p.add_argument("--window", action="store_true",
                   help="open the app in its own window (dropped files fill path fields; closing it keeps VideoForge in the "
                        "tray); needs the desktop extra")
    p.add_argument("--data-dir", type=Path, help="where the queue database lives (default: %%APPDATA%%/VideoForge)")
    p.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
