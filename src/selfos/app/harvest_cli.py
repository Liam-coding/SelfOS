"""app / harvest_cli responsibilities."""
import argparse
from pathlib import Path
from datetime import date
from selfos.app.staging import auto_generate_staging
from selfos.sources.digest import build_session_digest
from selfos.app.harvest import build_stats_report
from selfos.storage.onboarding import cleanup_old_digests
from selfos.storage.onboarding import ensure_vault_structure
from selfos.web.rendering.dashboard import generate_dashboard
from selfos.storage.onboarding import install_skill
from selfos.app.harvest import load_state
from selfos.app.harvest import resolve_since
from selfos.app.harvest import run_extraction
from selfos.app.harvest import save_state
from selfos.knowledge.scoring import score_vault

__version__ = "0.5.0"


def main():
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="SelfOS Harvest — build a self-portrait from AI conversation history"
    )
    parser.add_argument("--days", type=int, default=0,
                        help="Only include sessions from the last N days (default: all)")
    parser.add_argument("--full", action="store_true",
                        help="Force full re-extraction (ignore last-run state)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview extraction without writing any files")
    parser.add_argument("--stats", action="store_true",
                        help="Show per-project statistics without writing any files")
    parser.add_argument("--version", action="version", version=f"harvest {__version__}")
    from selfos.paths import AppPaths, project_root
    parser.add_argument("--root", type=Path, default=project_root())
    args = parser.parse_args()

    vault = AppPaths.from_root(args.root).vault
    inbox = vault / "90_Inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    import time as _time
    _start = _time.monotonic()

    print("SelfOS Harvest")

    # Ensure vault structure is complete
    created = ensure_vault_structure(vault)
    if created:
        print("  Created missing vault structure:")
        for item in created:
            print(item)

    # Auto-install /digest skill
    if install_skill():
        print("  /digest skill: ready")
    else:
        print("  /digest skill: not found (skill file missing)")

    state = load_state(vault)
    since = resolve_since(args.days, args.full, state)

    if args.days > 0:
        print(f"Extracting sessions from the last {args.days} days...")
    elif since is None:
        print("Extracting all sessions (full mode)...")
    else:
        print(f"Extracting sessions since last run ({since.strftime('%Y-%m-%d %H:%M UTC')})...")

    all_msgs, raw_count = run_extraction(vault, since)

    if not all_msgs:
        print("\nNo new messages since last run.")
        if since:
            print("Run with --full to re-extract everything.")
        return

    if args.dry_run:
        contexts = len(set(m["cwd"] or m["project"] for m in all_msgs))
        oldest = min(m["ts"] for m in all_msgs).strftime("%Y-%m-%d")
        newest = max(m["ts"] for m in all_msgs).strftime("%Y-%m-%d")
        print(f"\n[dry-run] Would write: vault/90_Inbox/{date.today()}-sessions-digest.md")
        print(f"  Messages : {len(all_msgs)}")
        print(f"  Contexts : {contexts}")
        print(f"  Date range: {oldest} → {newest}")
        print("  (no files written)")
        return

    if args.stats:
        print()
        print(build_stats_report(all_msgs))
        return

    digest = build_session_digest(all_msgs, raw_line_count=raw_count)
    out_path = inbox / f"{date.today()}-sessions-digest.md"
    out_path.write_text(digest, encoding="utf-8")

    # Persist last-run timestamp (use the latest message timestamp)
    latest_msg_ts = max(m["ts"] for m in all_msgs)
    state["last_run"] = latest_msg_ts.isoformat()
    save_state(vault, state)

    # Clean up old digests (keep last 7)
    deleted = cleanup_old_digests(inbox, keep=7)
    if deleted:
        print(f"  Cleaned up {deleted} old digest(s).")

    contexts = len(set(m["cwd"] or m["project"] for m in all_msgs))
    elapsed = _time.monotonic() - _start
    print(f"\nDone in {elapsed:.1f}s: {len(all_msgs)} msgs from {contexts} contexts "
          f"→ vault/90_Inbox/{out_path.name}")

    # Score vault and generate dashboard
    scores = score_vault(vault)
    dash = generate_dashboard(vault, scores)
    scored = [k for k, v in scores.items() if isinstance(v, int)]
    print(f"  Dashboard: {dash.relative_to(vault.parent)} "
          f"({len(scored)} dimensions scored)")

    # Auto-generate staging files via AI
    print("  Generating vault updates (AI)…", end=" ", flush=True)
    staged = auto_generate_staging(vault, out_path)
    if staged:
        print(f"{len(staged)} staging file(s) ready")
        for p in staged:
            print(f"    → {p.relative_to(vault.parent)}")
    else:
        print("none generated")

    print()
    print("Next — open Claude Code in this directory and say:")
    print(f'  "Read vault/90_Inbox/{out_path.name} and distribute insights to vault modules."')
