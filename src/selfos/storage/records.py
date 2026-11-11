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
        basis={'summary_context':'Saved-summary inference; verify raw sources for scope.',
               'project_context':'Legacy project context; event time and direct evidence unavailable.',
               'session_context':'Source conversation; date is the session time.'}.get(r.get('source_scope'))
        if basis:lines.append('  Basis: '+basis)
    return (outside+'\n\n'+start+'\n'+'\n'.join(lines)+'\n'+end+'\n').encode()


def record_writes(vault,state):
    from selfos.storage.pipeline import safe_path
    writes={}
    for category,path in FILES.items():
        actual=safe_path(Path(vault).resolve(),path)
        records=state.get(category,[])
        if category=='history':
            from selfos.knowledge.history import history_records
            records=history_records(state)
        old=actual.read_text(encoding='utf-8') if actual.exists() else ''
        writes[path]=managed_content(old,category.replace('_',' ').title(),records,category)
    return writes
