import json
import pytest
from selfos_auth import AuthManager

def manager(tmp_path):
    return AuthManager(tmp_path/'app',tmp_path/'app/vault',directory=tmp_path/'private')

def test_password_hash_sessions_and_deleted_file_fail_closed(tmp_path):
    a=manager(tmp_path)
    assert a.status()=='setup'
    a.setup('a sufficiently long password')
    raw=a.path.read_text()
    assert 'a sufficiently long password' not in raw and '$argon2id$' in raw
    token=a.login('a sufficiently long password')
    assert a.authenticated(token)
    assert not a.authenticated('wrong-token')
    a.path.unlink()
    assert a.status()=='locked' and not a.authenticated(token)
    with pytest.raises(ValueError):a.setup('another long password')

def test_existing_knowledge_needs_local_reset(tmp_path):
    a=manager(tmp_path);a.vault.mkdir(parents=True)
    (a.vault/'.knowledge_pipeline.json').write_text('{}')
    assert a.status()=='locked'
    a.reset('new sufficiently long password')
    assert a.authenticated(a.login('new sufficiently long password'))

def test_change_logout_corruption_and_replaced_hash(tmp_path):
    a=manager(tmp_path);a.setup('first sufficiently long password')
    token=a.login('first sufficiently long password')
    with pytest.raises(ValueError):a.change(token,'incorrect','second sufficiently long password')
    a.change(token,'first sufficiently long password','second sufficiently long password')
    assert not a.authenticated(token)
    token=a.login('second sufficiently long password');a.logout(token)
    assert not a.authenticated(token)
    token=a.login('second sufficiently long password');a.path.write_text('{broken')
    assert a.status()=='locked' and not a.authenticated(token)

def test_expiry_and_failed_login_throttling(tmp_path):
    a=manager(tmp_path);a.setup('a sufficiently long password')
    for _ in range(5):
        with pytest.raises(ValueError):a.login('incorrect')
    with pytest.raises(ValueError,match='wait'):a.login('a sufficiently long password')

@pytest.mark.parametrize('raw',['null','[]','"text"','{"version":1,"hash":null}','{"version":1,"hash":{}}','{"version":1,"hash":"$argon2id$v=19$m=999999999,t=3,p=1$invalid$invalid"}'])
def test_corrupt_credentials_fail_closed(tmp_path,raw):
    a=manager(tmp_path);a.directory.mkdir(parents=True);a.path.write_text(raw)
    assert a.status()=='locked'
    assert not a.authenticated('any-token')

def test_external_local_reset_invalidates_existing_sessions(tmp_path):
    a=manager(tmp_path);a.setup('first sufficiently long password')
    token=a.login('first sufficiently long password')
    manager(tmp_path).reset('second sufficiently long password')
    assert not a.authenticated(token)
    assert a.authenticated(a.login('second sufficiently long password'))

def test_manual_knowledge_requires_local_recovery(tmp_path):
    a=manager(tmp_path);a.vault.mkdir(parents=True);(a.vault/'PROFILE.md').write_text('Private profile')
    assert a.status()=='locked'
