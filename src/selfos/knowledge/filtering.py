"""Knowledge input filtering, independent of source parsing and transport."""

import copy
import json
import re
from selfos.sources.text import redact
from selfos.knowledge.identity import unique

def import_runtime_line(line):
    return bool(re.fullmatch(
        r'(?:SelfOS Knowledge: scanning local Claude Code and Codex conversations|'
        r'Scanned \d+ messages; compacted into \d+ session parts|'
        r'Knowledge: \d+ (?:messages, \d+ new batches|compact session parts, \d+ pending; workers \d+)|'
        r'Organizing (?:session|batch) \d+/\d+ \.\.\.|'
        r'Saved (?:session|batch) \d+/\d+(?:: \d+ facts)?; backup [A-Za-z0-9_-]+|'
        r'(?:Session|Batch) \d+, attempt \d+/\d+:.*|'
        r'Knowledge import failed:.*|Diagnostic: vault/\.knowledge_errors/.*|'
        r'Retrying generation with the validation error as repair feedback \.\.\.|'
        r'Batch not saved; completed earlier batches are preserved\. Retry remains available\.)',line.strip()))

def content_identity(message):
    if message.get("provenance") in ("quoted_dialogue","runtime_evidence","runtime_output","machine_summary","agent_status"):
        return message["provenance"]
    text = message.get("text", "").strip()
    if text and all(import_runtime_line(line) for line in text.splitlines() if line.strip()):
        return "runtime_output"
    head = text[:800]
    if head.startswith('<codex_internal_context') and text.endswith('</codex_internal_context>'):
        return 'machine_summary'
    if any(t in head for t in ("<local-command-stdout>", "<local-command-caveat>", "[external_agent_tool_result]")):
        return "runtime_output"
    if head.startswith(("This session is being continued from a previous conversation",
                        "Another language model started to solve this problem", "# Update Config Skill",
                        "Base directory for this skill:")):
        return "machine_summary"
    if any(t in head for t in ("当前子代理没有可调用的文件读取", "Agent errored: stream disconnected", "本次未完成有效审查")):
        return "agent_status"
    if message.get("provenance") == "quoted_dialogue" or (message.get("role") == "user" and (
        any(t in head for t in ("以下是之前 AI", "以下是AI", "GPT回答", "DeepSeek回答", "个人健身档案整理")) or
        (len(text) > 12000 and any(t in text for t in ("把这部分抽取", "ChatGPT", "DeepSeek", "用户：", "Assistant:"))))):
        return "quoted_dialogue"
    return "user_statement" if message.get("role") == "user" else "assistant_suggestion"

def transient_only(text):
    transient = {'继续','再跑一次','好的','谢谢','取消这次运行','先停一下','重试','帮我打开终端',
                 'continue','retry','run it again','thanks','ok','stop this run','open the terminal',
                 '/clear','/exit','git status','对','yes','好的，谢谢','ping',
                 '现在进行到哪里了','现在什么情况','怎么样了，可以继续吗','什么情况了'}
    normalized=text.strip().casefold().rstrip('.!。！？?')
    if normalized in transient:return True
    parts=[part.strip() for part in re.split(r'[.!。！？?;；,，]+',normalized.replace(chr(10),';')) if part.strip()]
    return bool(parts) and all(part in transient for part in parts)

def compact_message(message):
    if message.get("role") == "tool" and not message.get("verification", {}).get("relevant"):
        return None
    text = redact(message["text"]).strip()
    provenance = content_identity(message)
    if provenance in ("runtime_output", "machine_summary", "agent_status"):
        if not message.get("verification", {}).get("relevant"):
            evidence = unique(line.strip()[:400] for line in text.splitlines() if re.search(
                r"FAILED\s+test_|(?:ValueError|RuntimeError|AssertionError|TimeoutError):|"
                r"^(?:Session|Batch) \d+, attempt \d+/\d+:|^Knowledge import failed:", line))[:8]
            if provenance != "runtime_output" or not evidence:
                return None
            text = "Runtime failure evidence (not a user statement):\n" + "\n".join(evidence)
            provenance = "runtime_evidence"
    if transient_only(text):
        return None
    def code(match):
        body = match.group(1)
        symbols = re.findall(r"(?:def|function|class|CREATE TABLE|void)\s+([A-Za-z_][\w]*)", body, re.I)
        return "[Code omitted; symbols: " + ", ".join(dict.fromkeys(symbols))[:600] + "]"
    text = re.sub(r"```[^\n]*\n(.*?)```", code, text, flags=re.S)
    # Parse complete bulk JSON documents, retaining surrounding purpose and outcome prose.
    decoder = json.JSONDecoder()
    position = 0
    while position < len(text):
        match = re.search(r"[\[{]", text[position:])
        if not match:
            break
        start = position + match.start()
        try:
            value, end = decoder.raw_decode(text, start)
        except ValueError:
            position = start + 1
            continue
        if end - start > 1200:
            keys = list(value)[:12] if isinstance(value, dict) else list(value[0])[:12] if value and isinstance(value[0], dict) else []
            replacement = "[Bulk JSON omitted; fields: " + ", ".join(map(str, keys)) + "]"
            text = text[:start] + replacement + text[end:]
            position = start + len(replacement)
        else:
            position = end
    # Keep explanatory prose on both sides; do not truncate the outcome at the tail.
    lines = text.splitlines()
    failures = unique(re.sub(r"^\s*\d{4}-\d\d-\d\d\S*\s*", "", line.strip())[:300]
                      for line in lines if re.match(r"^\s*\d{4}-\d\d-\d\d", line) and
                      re.search(r"ERROR|FAILED|Exception|Error:", line))[:6]
    text = "\n".join(line for line in lines if not re.match(
        r"^\s*(?:\{\"|\d{4}-\d\d-\d\d[T ]|[+\-]\s*(?:const |import |def )|\s*at .*:\d+)", line)
        and (not import_runtime_line(line) or re.match(r'^(?:Session|Batch) \d+, attempt \d+/\d+:|^Knowledge import failed:',line)))
    text = text.strip()
    if failures:
        text += "\nFailure evidence:\n" + "\n".join(failures)
    if not text or re.fullmatch(r"\[Code omitted; symbols: .*\]", text):
        return None
    return {**copy.deepcopy(message), "text": text, "provenance": provenance}
