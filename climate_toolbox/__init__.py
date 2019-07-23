# -*- coding: utf-8 -*-

"""Top-level package for climate_toolbox."""

__author__ = """Justin Simcock"""
__email__ = 'jsimcock@rhg.com'
__version__ = '0.1.4'

import pkgutil

__all__ = []
for loader, module_name, is_pkg in  pkgutil.walk_packages(__path__):
    __all__.append(module_name)
    _module = loader.find_module(module_name).load_module(module_name)
    globals()[module_name] = _module

    
print __all__