"""storage / records responsibilities."""
import re
from pathlib import Path
from selfos.knowledge.settings import FILES

def managed_content(old,title,records,marker):
    start='<!-- selfos-managed-'+marker+' -->';end='<!-- /selfos-managed-'+marker+' -->'
    outside=re.sub(re.escape(start)+r'.*?'+re.escape(end),'',old,flags=re.S).rstrip() if start in old else old.rstrip()
    if not outside:outside='# '+title
    lines=[]
    for r in records:
        lines.extend(['- ['+r.get('kind','inference')+'] '+r['text']+(' [conflict]' if r.get('conflict') else ''),
                      '  Date: '+r.get('observed_at',''), '  Source: '+', '.join(r['source_ids'])])
        if r.get('project_title'):lines.append('  Project: '+r['project_title'])
        if r.get('supporting_source_ids'):lines.append('  Supporting sources: '+', '.join(r['supporting_source_ids']))
        if r.get('context_source_ids'):lines.append('  Context sources: '+', '.join(r['context_source_ids']))
        if r.get('claim_type'):lines.append('  Claim type: '+r['claim_type'])
        if r.get('retention_reason'):lines.append('  Retention warning: '+r['retention_reason'])
        if 'scope_type' in r:
            lines.append('  Scope: '+r['scope_type']+':'+r.get('scope','unknown'))
        for field,label in (('valid_from','Valid from'),('valid_until','Valid until')):
            if r.get(field):lines.append('  '+label+': '+r[field])
        if r.get('validity_source_ids'):lines.append('  Validity sources: '+', '.join(r['validity_source_ids']))
        if r.get('scheduled'):lines.append('  Planned change; not yet active.')
        if r.get('validity_conflict'):lines.append('  Effective dates conflict; check original sources.')
        if r.get('superseded_by_source_ids'):
            lines.append('  Superseded by sources: '+', '.join(r['superseded_by_source_ids']))
        if r.get('conflict_source_ids'):
            lines.append('  Conflicting sources: '+', '.join(r['conflict_source_ids']))
        basis={'summary_context':'Saved-summary inference; verify raw sources for scope.',
               'project_context':'Legacy project context; event time and direct evidence unavailable.',
               'session_context':'Source conversation; date is the session time.'}.get(r.get('source_scope'))
        if basis:lines.append('  Basis: '+basis)
    return (outside+'\n\n'+start+'\n'+'\n'.join(lines)+'\n'+end+'\n').encode()


def record_writes(vault,state,*,corrections=None):
    from selfos.knowledge.preferences import preference_snapshot
    state=preference_snapshot(state)
    from selfos.knowledge.corrections import apply_corrections
    from selfos.storage.corrections import load_corrections
    ledger=load_corrections(vault) if corrections is None else corrections
    generated=state
    state=apply_corrections(state,ledger)
    from selfos.storage.pipeline import safe_path
    writes={}
    for category,path in FILES.items():
        actual=safe_path(Path(vault).resolve(),path)
        records=[record for record in state.get(category,[]) if category!='preferences' or not record.get('scheduled')]
        if category=='history':
            from selfos.knowledge.history import history_records
            records=history_records(state)
        old=actual.read_text(encoding='utf-8') if actual.exists() else ''
        writes[path]=managed_content(old,category.replace('_',' ').title(),records,category)
    if any(action.get('active',True) and action.get('category')=='lessons' for action in ledger.get('actions',[])):
        path='05_Life/lessons.md'
        actual=safe_path(Path(vault).resolve(),path)
        old=actual.read_text(encoding='utf-8') if actual.exists() else '# Reusable lessons'
        if '<!-- selfos-managed-lessons -->' not in old:
            # Remove only exact generator blocks; preserve unrelated manual prose.
            for lesson in generated.get('lessons',[]):
                block='- ['+lesson.get('kind','inference')+'] '+lesson['text']+chr(10)+'  Source: '+', '.join(lesson.get('source_ids',[]))
                old=old.replace(block,'')
        writes[path]=managed_content(old,'Reusable lessons',state.get('lessons',[]),'lessons')
    return writes
