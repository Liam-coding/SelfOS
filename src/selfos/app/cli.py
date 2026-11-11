"""Console entry points; import each command only after root selection."""
import os
import sys
from importlib import import_module

COMMANDS = {'serve':'selfos.web.server', 'knowledge':'selfos.app.knowledge_cli',
            'harvest':'selfos.app.harvest_cli', 'auth':'selfos.security.auth'}

def run(command):
    args = sys.argv[1:]
    for index, value in enumerate(args):
        if value == '--root' and index + 1 < len(args):
            os.environ['SELFOS_ROOT'] = args[index + 1]
        elif value.startswith('--root='):
            os.environ['SELFOS_ROOT'] = value.split('=', 1)[1]
    import_module(COMMANDS[command]).main()

def serve(): run('serve')
def knowledge(): run('knowledge')
def harvest(): run('harvest')
def auth(): run('auth')

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print('Usage: python -m selfos {serve,knowledge,harvest,auth} [options]')
        raise SystemExit(0 if len(sys.argv) > 1 and sys.argv[1] in ('-h','--help') else 2)
    command = sys.argv.pop(1)
    run(command)
