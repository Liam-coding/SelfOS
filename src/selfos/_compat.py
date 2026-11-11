"""Compatibility only: package code must never import legacy facades."""
from importlib import import_module
import sys
from types import ModuleType

class LegacyModule(ModuleType):
    def __getattr__(self, name):
        target = self._exports.get(name)
        if target is None: raise AttributeError(name)
        module, symbol = target
        return getattr(import_module('selfos.' + module), symbol)

    def __setattr__(self, name, value):
        target = self.__dict__.get('_exports', {}).get(name)
        if target is not None:
            module, symbol = target
            owner = import_module('selfos.' + module)
            previous = getattr(owner, symbol)
            # Legacy callers patched globals in a monolithic module. Forward
            # those assignments to already loaded consumers of the same symbol.
            for loaded_name, loaded in list(sys.modules.items()):
                if loaded_name.startswith('selfos.') and loaded is not None:
                    if loaded.__dict__.get(symbol, object()) is previous:
                        setattr(loaded, symbol, value)
            setattr(owner, symbol, value)
        else: super().__setattr__(name, value)

    def __dir__(self):
        return sorted(set(super().__dir__()) | set(self._exports))

def attach(name, exports):
    module = sys.modules[name]
    module.__class__ = LegacyModule
    module._exports = exports
    module.__all__ = [name for name in exports if not name.startswith('_')]
