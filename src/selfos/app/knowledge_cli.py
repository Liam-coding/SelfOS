"""app / knowledge_cli responsibilities."""
from selfos.providers.knowledge import api_refiner
from selfos.providers.knowledge import api_summarizer
from selfos.sources.conversations import extract_conversations
from selfos.sources.conversations import local_roots
from selfos.storage.legacy import restore_backup
import argparse
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description='SelfOS: one-click local conversations to personal knowledge')
    from selfos.paths import AppPaths
    parser.add_argument('--root', type=Path, help='Application and model configuration root')
    parser.add_argument('--vault', type=Path)
    parser.add_argument('--restore', metavar='RUN_ID', help='Restore a knowledge import from its backup')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--rebuild', action='store_true')
    parser.add_argument('--restore-last', action='store_true')
    parser.add_argument('--stop-file', type=Path)
    parser.add_argument('--dry-run', action='store_true', help='Scan and compact without API requests or vault writes')
    parser.add_argument('--onboarding-preview', help='Process only a validated bounded local preview; resume keeps its allowance')
    parser.add_argument('--upload-preview', help='Process only selected uploaded document parts; never scan local Harnesses')
    parser.add_argument('--native-preview', help='Process only a verified bounded OpenCode native preview')
    args = parser.parse_args()
    if args.native_preview and (args.upload_preview or args.onboarding_preview or args.rebuild or args.restore or args.restore_last):
        parser.error('Native preview cannot be mixed with another selection or restore')
    if args.upload_preview and (args.onboarding_preview or args.rebuild or args.restore or args.restore_last):
        parser.error('Uploaded documents cannot be mixed with another import or restore')
    paths = AppPaths.from_root(args.root)
    # A root explicitly selects configuration independently of vault location.
    # Legacy --vault-only commands continue using that vault's parent directory.
    config_root = paths.root if args.root is not None or args.vault is None else args.vault.resolve().parent
    args.vault = args.vault.resolve() if args.vault is not None else paths.vault
    try:
        if args.restore_last:
            from selfos.app.knowledge import restore_last
            print(json.dumps(restore_last(args.vault)), flush=True)
            return
        if args.restore:
            from selfos.storage.pipeline import restore_pipeline_backup
            if list((args.vault / '.knowledge_backups' / args.restore).glob('*/pipeline-manifest.json')):
                restore_pipeline_backup(args.vault, args.restore)
            else:
                restore_backup(args.vault, args.restore)
            print(f'Restored knowledge import {args.restore}', flush=True)
            return
        print('SelfOS Knowledge: organizing selected uploaded documents' if args.upload_preview else
              'SelfOS Knowledge: organizing selected OpenCode preview' if args.native_preview else
              'SelfOS Knowledge: scanning local Claude Code and Codex conversations', flush=True)
        cancelled = lambda: bool(args.stop_file and args.stop_file.exists())
        preview = None
        budget = None
        if args.native_preview:
            from selfos.app.harness_imports import resolve_native
            preview = resolve_native(args.vault, args.native_preview)
        if args.upload_preview is not None:
            from selfos.app.upload_preview import resolve_upload_preview
            preview = resolve_upload_preview(args.vault, args.upload_preview)
        if args.onboarding_preview is not None:
            from selfos.app.onboarding import resolve_preview
            from selfos.storage.onboarding import SampleBudget
            preview = resolve_preview(args.vault, args.onboarding_preview)
            budget = SampleBudget(args.vault, args.onboarding_preview)
        if not args.dry_run:
            from selfos.app.knowledge import run_knowledge
            if args.native_preview:
                from selfos.app.harness_imports import organize_native
                result = organize_native(args.vault, args.native_preview,
                    summarize=api_summarizer(config_root), refine=api_refiner(config_root, cancel=cancelled),
                    max_workers=args.workers, cancel=cancelled, progress=lambda line: print(line, flush=True))
            elif args.upload_preview:
                from selfos.app.uploads import organize_uploads
                result = organize_uploads(args.vault, args.upload_preview, config_root=config_root,
                    max_workers=args.workers, cancel=cancelled, progress=lambda line: print(line, flush=True))
            else:
                summarizer = api_summarizer(config_root,budget=budget)
                refiner = api_refiner(config_root,cancel=cancelled,budget=budget)
                result = run_knowledge(args.vault, rebuild=args.rebuild, max_workers=args.workers,
                    summarize=summarizer, refine=refiner, sample_id=args.onboarding_preview,
                    cancel=cancelled,
                    progress=lambda line: print(line, flush=True))
            if result['installed']:
                from selfos.web.rendering.dashboard import generate_dashboard
                generate_dashboard(args.vault)
            print(f"Knowledge {result['status']}: {result['model_calls']} API calls; operation {result['operation_id']}", flush=True)
            if result['status'] != 'completed':
                raise SystemExit(2)
            return
        from selfos.sources.compaction import prepare_sessions
        cancelled = lambda: bool(args.stop_file and args.stop_file.exists())
        if preview is not None:
            sessions = preview['sessions']
            messages = [m for s in sessions for m in s['messages']]
        else:
            roots = local_roots()
            if (args.vault / '.knowledge_sources.json').exists():
                from selfos.sources.selection import load_sources, allowed_source
                selection = load_sources(args.vault)
                roots = [path for directory in selection['roots'] for path in Path(directory).rglob('*.jsonl')
                         if path.is_file() and allowed_source(path, selection)]
            messages = extract_conversations(roots, cancel=cancelled)
        state_file = args.vault / '.knowledge_pipeline.json'
        aliases = json.loads(state_file.read_text(encoding='utf-8')).get('project_aliases', {}) if state_file.exists() else {}
        if preview is None:
            sessions = prepare_sessions(messages, max_chars=24000, cancel=cancelled, aliases=aliases)
        print(f'Scanned {len(messages)} messages; compacted into {len(sessions)} session parts, {len({s["project_id"] for s in sessions})} projects; characters {sum(len(m["text"]) for m in messages)} -> {sum(len(m["text"]) for s in sessions for m in s["messages"])}', flush=True)
        return
    except Exception as exc:
        print(f'Knowledge import failed: {exc}', flush=True)
        raise SystemExit(1)
