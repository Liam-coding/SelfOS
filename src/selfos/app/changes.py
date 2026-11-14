"""Read-only, bounded traversal from the authenticated canonical audit head."""
import re
from pathlib import Path
from selfos.storage.files import _locked
from selfos.storage.transactions import recover
from selfos.storage.change_receipts import read_head,read_root,read_json,receipt_folder,PART_LIMIT,encode,sha
from selfos.storage.change_cursors import save,load

ROOTS_PER_REQUEST=100
PARTS_PER_REQUEST=32
BYTES_PER_REQUEST=16*1024*1024
CATEGORIES=('all','projects','personal_facts','preferences','lessons','history')
ACTIONS=('all','added','updated','removed','invalidated','superseded','merged','restored')

def event_id(ref):return ref['run_id']+':'+str(ref['index'])

def _head(vault):
    with _locked(Path(vault).resolve()):
        recover(vault)
        return read_head(vault)

def _context(vault,session,head,cursor):
    revision=sha(encode(head))
    if cursor:
        context=load(vault,session,cursor)
        if context['revision']!=revision:return None
        return context
    return {'revision':revision,'next':head['audit_tip'] if head else None,'proofs':{},'reverted':[],
            'scanned':0,'filters':None,'boundary':head.get('omitted_parent') if head else None}

def _unchanged(vault,context):
    return sha(encode(_head(vault)))==context['revision']

def _reset(vault,session):
    context=_context(vault,session,_head(vault),None)
    return {'status':'reset_required','reset_required':True,'items':[],'cursor':save(vault,session,context)}

class _Budget:
    def __init__(self):self.roots=0;self.parts=0;self.bytes=0;self.cached={}
    def root(self,vault,ref):
        key=sha(encode(ref))
        if key in self.cached:return self.cached[key]
        size=(receipt_folder(vault,ref)/'change-receipt.json').stat().st_size
        if self.roots>=ROOTS_PER_REQUEST or self.bytes+size>BYTES_PER_REQUEST:return None
        self.roots+=1;self.bytes+=size
        self.cached[key]=read_root(vault,ref)
        return self.cached[key]
    def part(self,vault,ref,part):
        if self.parts>=PARTS_PER_REQUEST or self.bytes+part['bytes']>BYTES_PER_REQUEST:return None
        self.parts+=1;self.bytes+=part['bytes']
        path=receipt_folder(vault,ref)/f"changes-{part['number']:06d}.json"
        if path.stat().st_size!=part['bytes']:raise ValueError('Change part size mismatch')
        result=read_json(path,PART_LIMIT,part['hash'])
        if result.get('version')!=1 or not isinstance(result.get('changes'),list) or not isinstance(result.get('sources'),dict):
            raise ValueError('Invalid change part')
        return result

def _advance(vault,context,budget):
    ref=context['next']
    if ref is None or ref==context['boundary']:return None
    root=budget.root(vault,ref)
    if root is None:return None
    ident=event_id(ref)
    if ident in context['proofs']:raise ValueError('Cyclic change ancestry')
    context['proofs'][ident]=ref
    context['next']=root['audit_parent']
    context['scanned']+=1
    for reverted in root.get('reverted_receipts',[]):
        if reverted not in context['reverted']:context['reverted'].append(reverted)
    return ref,root

def _state(context,ref,root):
    return 'reverted' if ref in context['reverted'] else 'restore' if root['kind']=='restore' else 'applied'

def list_changes(vault,*,session,cursor=None,category='all',action='all',conflict=False):
    if category not in CATEGORIES or action not in ACTIONS or not isinstance(conflict,bool):raise ValueError('Invalid change filters')
    head=_head(vault);context=_context(vault,session,head,cursor)
    if context is None:return _reset(vault,session)
    filters=[category,action,conflict]
    if context['filters'] is not None and context['filters']!=filters:raise ValueError('History cursor filters changed')
    context['filters']=filters
    budget=_Budget();items=[]
    while True:
        pair=_advance(vault,context,budget)
        if pair is None:break
        ref,root=pair
        if ((category!='all' and not root.get('category_counts',{}).get(category))
            or (action!='all' and not root['counts'].get(action)) or (conflict and not root['conflict_count'])):continue
        items.append({'id':event_id(ref),'recorded_at':root['recorded_at'],'kind':root['kind'],'counts':root['counts'],
            'change_count':root['change_count'],'conflict_count':root['conflict_count'],'state':_state(context,ref,root)})
    more=context['next'] is not None and context['next']!=context['boundary']
    if not _unchanged(vault,context):return _reset(vault,session)
    return {'status':'verified','items':items,'total':context['scanned'] if not more and not context['boundary'] else None,
            'scanned':budget.roots,'has_more':more,'boundary':bool(context['boundary'] and not more),
            'cursor':save(vault,session,context)}

def _proof(vault,event,session,cursor):
    if not isinstance(event,str) or not re.fullmatch(r'[0-9]{8}T[0-9]{6}-[a-f0-9]{12}:[0-9]{1,6}',event):
        raise ValueError('Invalid change operation identity')
    head=_head(vault);context=_context(vault,session,head,cursor)
    if context is None:return None,None,_reset(vault,session)
    budget=_Budget()
    while event not in context['proofs']:
        if _advance(vault,context,budget) is None:break
    if event not in context['proofs']:
        more=context['next'] is not None and context['next']!=context['boundary']
        if not _unchanged(vault,context):return None,None,_reset(vault,session)
        return context,budget,{'status':'verification_pending' if more else 'not_included' if context['boundary'] else 'missing',
            'cursor':save(vault,session,context),'has_more':more}
    return context,budget,None

def change_detail(vault,event_id,*,session,cursor=None):
    context,budget,error=_proof(vault,event_id,session,cursor)
    if error:return error
    ref=context['proofs'][event_id]
    root=budget.root(vault,ref)
    if root is None:return {'status':'verification_pending','cursor':save(vault,session,context),'has_more':True}
    position=context.get('detail_position',0) if context.get('detail_event')==event_id else 0
    items=[]
    for part in root['parts'][position:]:
        payload=budget.part(vault,ref,part)
        if payload is None:break
        items.extend(payload['changes']);position+=1
    context.update(detail_event=event_id,detail_position=position)
    if not _unchanged(vault,context):return _reset(vault,session)
    return {'status':'verified','id':event_id,'kind':root['kind'],'recorded_at':root['recorded_at'],
        'counts':root['counts'],'state':_state(context,ref,root),'items':items,'has_more':position<len(root['parts']),
        'reverted_receipts':[globals()['event_id'](ref) for ref in root['reverted_receipts']],
        'cursor':save(vault,session,context)}

def change_source(vault,event_id,source_id,*,session,proof,offset=0,limit=24000):
    context,budget,error=_proof(vault,event_id,session,proof)
    if error:return error
    ref=context['proofs'][event_id]
    root=budget.root(vault,ref)
    if root is None:return {'status':'verification_pending','cursor':save(vault,session,context)}
    position=context.get('source_position',0) if context.get('source_event')==[event_id,source_id] else 0
    for part in root['parts'][position:]:
        payload=budget.part(vault,ref,part)
        if payload is None:
            context.update(source_event=[event_id,source_id],source_position=position)
            return {'status':'verification_pending','cursor':save(vault,session,context)}
        position+=1
        source=payload['sources'].get(source_id)
        if source is not None:
            from selfos.app.library import knowledge_source_metadata
            result=knowledge_source_metadata(vault,source_id,source,offset=offset,limit=limit)
            if not _unchanged(vault,context):return _reset(vault,session)
            return {'status':'verified',**result}
    return {'status':'source_missing'}


def record_change(vault,version,*,session,cursor=None):
    """Find the newest linked version through the same bounded published ancestry."""
    if not isinstance(version,str) or not re.fullmatch('[a-f0-9]{64}',version):raise ValueError('Invalid knowledge record version')
    context=_context(vault,session,_head(vault),cursor)
    if context is None:return _reset(vault,session)
    if context.get('record_version',version)!=version:raise ValueError('History record cursor changed')
    context['record_version']=version
    budget=_Budget()
    while True:
        ref=context.get('record_ref')
        if ref is None:
            pair=_advance(vault,context,budget)
            if pair is None:break
            ref,root=pair;position=0
        else:
            root=budget.root(vault,ref)
            if root is None:break
            position=context.get('record_position',0)
        for part in root['parts'][position:]:
            payload=budget.part(vault,ref,part)
            if payload is None:
                context.update(record_ref=ref,record_position=position)
                if not _unchanged(vault,context):return _reset(vault,session)
                return {'status':'verification_pending','has_more':True,'cursor':save(vault,session,context)}
            position+=1
            if any(snapshot['version_id']==version for change in payload['changes'] for snapshot in change['before']+change['after']):
                if not _unchanged(vault,context):return _reset(vault,session)
                return {'status':'verified','id':event_id(ref),'cursor':save(vault,session,context)}
        context.pop('record_ref',None);context.pop('record_position',None)
    if not _unchanged(vault,context):return _reset(vault,session)
    more=context['next'] is not None and context['next']!=context['boundary']
    return {'status':'verification_pending' if more else 'not_included' if context['boundary'] else 'missing',
            'has_more':more,'cursor':save(vault,session,context)}
