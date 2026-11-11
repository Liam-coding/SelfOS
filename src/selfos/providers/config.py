"""providers / config responsibilities."""
from pathlib import Path

def _get_api_config(root: Path) -> tuple[str, str]:
    from selfos.providers.settings import load_config
    c=load_config(root)
    return c['api_key'],c['base_url'].rstrip('/')
