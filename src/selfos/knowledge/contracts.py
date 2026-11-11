"""knowledge / contracts responsibilities."""
import json
import re

TARGETS = (
    'PROFILE.md', 'NOW.md', 'GOALS.md', 'DECISIONS.md',
    '01_Career/profile.md', '02_Work/knowledge.md', '03_Research/knowledge.md',
    '04_Health_Fitness/log.md', '05_Life/learning.md', '05_Life/knowledge.md',
)


STATE = '.knowledge_state.json'


SOURCES = '.knowledge_sources.json'


class ResponseFormatError(ValueError):
    """Invalid model response with raw content retained only for local diagnostics."""
    def __init__(self, message, raw_response=''):
        super().__init__(message)
        self.raw_response = raw_response


def _parse_model_json(raw):
    """Parse one unambiguous JSON document without repairing malformed JSON."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    fence = chr(96) * 3
    pattern = re.compile(r'(?:^|\n)[ \t]*' + fence +
                         r'(?:json)?[ \t]*\r?\n(.*?)\r?\n[ \t]*' + fence +
                         r'[ \t]*(?=\r?\n|$)', re.DOTALL | re.IGNORECASE)
    blocks = list(pattern.finditer(raw))
    try:
        if blocks:
            if len(blocks) != 1:
                raise ValueError('multiple JSON blocks')
            block = blocks[0]
            outside = raw[:block.start()] + raw[block.end():]
            if fence in outside or raw[:block.start()].lstrip().startswith(('[', '{')):
                raise ValueError('multiple candidate documents')
            if raw[block.end():].lstrip().startswith(('[', '{')):
                raise ValueError('multiple candidate documents')
            return json.loads(block.group(1).strip())
        if raw.startswith(('[', '{')) and fence not in raw:
            value, end = json.JSONDecoder().raw_decode(raw)
            tail = raw[end:].strip()
            if tail.startswith(('[', '{')):
                raise ValueError('multiple candidate documents')
            return value
    except ValueError as error:
        raise ResponseFormatError('AI response contains malformed or ambiguous JSON; return exactly one complete JSON array.', raw) from error
    raise ResponseFormatError('AI response has no valid JSON document; return a JSON array, or [] when there are no facts.', raw)
