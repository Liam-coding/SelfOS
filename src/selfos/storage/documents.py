"""storage / documents responsibilities."""
import re
from selfos.knowledge.identity import digest
from selfos.storage.pipeline import safe_path

def render_card(card):
    lines = ["# " + card["title"], "", "[ai-inference] Project summary",
             "Project: " + card["project_id"], "Updated: " + card["updated_at"],
             "Status: " + card["status"], "Verified: " + str(card["verified"]), "", card["intent"]]
    for field in ("blockers", "next_steps", "decisions"):
        lines.extend(["", "## " + field, *["- " + v for v in card[field]]])
    lines.extend(["", "Sources stored in .knowledge_pipeline.json: " + str(len(card["source_ids"])),
                  "Source: " + ", ".join(card["source_ids"][:8]), ""])
    return "\n".join(lines).encode()


def _project_unmanaged(vault, identity, previous=None):
    path=safe_path(vault,'02_Work/projects/'+digest(identity)+'.md')
    if not path.exists():return ''
    text=path.read_text(encoding='utf-8')
    start='<!-- selfos-managed-project-card -->'
    end='<!-- /selfos-managed-project-card -->'
    if start in text and end in text:
        return re.sub(re.escape(start)+r'.*?'+re.escape(end),'',text,flags=re.S)
    if previous is not None:
        generated=render_card(previous).decode('utf-8')
        if text.startswith(generated):return text[len(generated):]
    # Unrecognized legacy edits are retained intact, never guessed away.
    return text


def render_project_document(vault, card, previous=None):
    outside=_project_unmanaged(vault,card['project_id'],previous).rstrip()
    return (outside+('\n\n' if outside else '')+'<!-- selfos-managed-project-card -->\n'+
            render_card(card).decode('utf-8')+'<!-- /selfos-managed-project-card -->\n').encode('utf-8')
