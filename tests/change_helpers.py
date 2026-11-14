"""Install synthetic fixture changes through the canonical audit boundary."""
import json
import uuid
from datetime import datetime,timezone

def install_fixture(vault,state):
    from selfos.app.change_publication import publish_changes
    run=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:12]
    publish_changes(vault,{'.knowledge_pipeline.json':json.dumps(state).encode()},run,1,kind='import')
