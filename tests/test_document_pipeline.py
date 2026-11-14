"""Uploaded-source provenance must survive real pipeline commits and cached runs."""
import hashlib
import json

from selfos.app.knowledge import run_knowledge
from selfos.app.library import knowledge_source
from selfos.sources.selection import save_sources
from tests.test_knowledge_service import summarize, refine


def document(tmp_path):
    vault=tmp_path/'vault'
    path=vault/'.knowledge_uploads/originals'/'synthetic.txt'
    path.parent.mkdir(parents=True)
    raw=b'I prefer Chinese. We are building reliable import.'
    path.write_bytes(raw)
    roots=tmp_path/'sources';roots.mkdir()
    save_sources(vault,{'roots':[str(roots)],'exclusions':[]})
    message={'id':'upload-fixture','text':raw.decode(),'path':str(path.relative_to(vault)),
        'timestamp':'2026-01-01T00:00:00Z','source':'uploaded_file','role':'document',
        'provenance':'quoted_dialogue','project_id':'synthetic-upload-project',
        'project':'Synthetic upload project','session_id':'synthetic-upload-session',
        'original_filename':'Synthetic source.txt','content_sha256':hashlib.sha256(raw).hexdigest()}
    return vault,path,message


def test_imported_document_remains_readable_from_its_original_source(tmp_path):
    vault,path,message=document(tmp_path);original=path.read_bytes()
    result=run_knowledge(vault,roots=[],selected_messages=[message],summarize=summarize,refine=refine)
    assert result['installed']
    source=knowledge_source(vault,message['id'])
    assert source['file']=='Synthetic source.txt'
    assert source['text']==original.decode()
    assert path.read_bytes()==original


def test_cached_import_restores_missing_document_metadata_without_generation(tmp_path):
    vault,path,message=document(tmp_path)
    run_knowledge(vault,roots=[],selected_messages=[message],summarize=summarize,refine=refine)
    state_path=vault/'.knowledge_pipeline.json'
    state=json.loads(state_path.read_text(encoding='utf-8'))
    for key in ('content_sha256','original_filename'):state['sources'][message['id']].pop(key,None)
    from tests.change_helpers import install_fixture
    install_fixture(vault,state)
    def unexpected(_):raise AssertionError('Metadata repair must reuse cached generation')
    result=run_knowledge(vault,roots=[],selected_messages=[message],summarize=unexpected,refine=unexpected)
    assert result['status']=='completed' and result['model_calls']==0
    assert knowledge_source(vault,message['id'])['file']=='Synthetic source.txt'
    assert path.read_bytes()==message['text'].encode()


def test_existing_document_identity_cannot_be_rebound_to_changed_original(tmp_path):
    vault,path,message=document(tmp_path)
    run_knowledge(vault,roots=[],selected_messages=[message],summarize=summarize,refine=refine)
    state_path=vault/'.knowledge_pipeline.json';before=state_path.read_bytes()
    path.write_bytes(b'Changed original content')
    changed={**message,'text':path.read_text(),'content_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    calls=[]
    def unexpected(item):calls.append(item);raise AssertionError('No generation before immutable source check')
    result=run_knowledge(vault,roots=[],selected_messages=[changed],summarize=unexpected,refine=unexpected)
    assert result['status']=='failed' and calls==[]
    assert state_path.read_bytes()==before


def test_multiple_messages_from_one_original_verify_file_once(tmp_path,monkeypatch):
    vault,path,message=document(tmp_path)
    from selfos.sources import documents
    actual=documents.document_source;reads=[]
    def observe(*args,**kwargs):reads.append(args[1]['path']);return actual(*args,**kwargs)
    monkeypatch.setattr(documents,'document_source',observe)
    second={**message,'id':'upload-second-message','timestamp':'2026-01-01T00:01:00Z'}
    result=run_knowledge(vault,roots=[],selected_messages=[message,second],summarize=summarize,refine=refine)
    assert result['installed'] and len(reads)==1


def test_later_processed_input_cannot_drop_known_document_metadata(tmp_path):
    vault,path,message=document(tmp_path)
    run_knowledge(vault,roots=[],selected_messages=[message],summarize=summarize,refine=refine)
    incoming={key:value for key,value in message.items() if key not in ('content_sha256','original_filename')}
    incoming['timestamp']='2026-01-02T00:00:00Z'
    result=run_knowledge(vault,roots=[],selected_messages=[incoming],summarize=summarize,refine=refine)
    assert result['installed']
    assert knowledge_source(vault,message['id'])['file']=='Synthetic source.txt'


def test_known_quoted_document_cannot_be_promoted_to_user_statement(tmp_path):
    vault,path,message=document(tmp_path)
    run_knowledge(vault,roots=[],selected_messages=[message],summarize=summarize,refine=refine)
    state_path=vault/'.knowledge_pipeline.json';before=state_path.read_bytes()
    promoted={**message,'role':'user','provenance':'user_statement'}
    calls=[]
    def unexpected(item):calls.append(item);return summarize(item)
    result=run_knowledge(vault,roots=[],selected_messages=[promoted],summarize=unexpected,refine=refine)
    assert result['status']=='failed' and calls==[]
    assert state_path.read_bytes()==before


def test_known_upload_identity_cannot_bypass_checks_as_a_harness_source(tmp_path):
    vault,path,message=document(tmp_path)
    run_knowledge(vault,roots=[],selected_messages=[message],summarize=summarize,refine=refine)
    state_path=vault/'.knowledge_pipeline.json';before=state_path.read_bytes()
    relabeled={**message,'source':'codex','role':'user','provenance':'user_statement'}
    calls=[]
    def unexpected(item):calls.append(item);return summarize(item)
    result=run_knowledge(vault,roots=[],selected_messages=[relabeled],summarize=unexpected,refine=refine)
    assert result['status']=='failed' and calls==[]
    assert state_path.read_bytes()==before


def test_default_document_provenance_stays_compatible_with_cached_replay(tmp_path):
    vault,path,message=document(tmp_path);message.pop('provenance')
    first=run_knowledge(vault,roots=[],selected_messages=[message],summarize=summarize,refine=refine)
    assert first['installed']
    def unexpected(_):raise AssertionError('Unchanged document should reuse cached generation')
    repeated=run_knowledge(vault,roots=[],selected_messages=[message],summarize=unexpected,refine=unexpected)
    assert repeated['status']=='completed' and repeated['model_calls']==0
    assert knowledge_source(vault,message['id'])['file']=='Synthetic source.txt'
