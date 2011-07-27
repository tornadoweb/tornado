'''
Created on 27 Jul 2011

@author: simon
'''

import os.path
import tornado.web
import sys
import types

class StaticFileFinder(object):
    """Base class for classes that search for absolute file paths 
    
    All subclasses should simply implement the find method
    """
    def find(self, path):
        """Returns the absolute path of a file given the path relative to the
        Application web root"""
        raise NotImplementedError


class FileSystemFinder(StaticFileFinder):
    """Searches for a file in the file system by appending the given path to a
    list of base paths, returning the first absolute path that exists."""
    def __init__(self, roots):
        if isinstance(roots, basestring):
            self.roots = [roots]
        else:
            self.roots = roots
    
    def find(self, path):
        for root in self.roots:
            current_path = os.path.join(root, path)
            if os.path.exists(current_path):
                return current_path


class UIModuleFinder(FileSystemFinder):
    """Uses all of the `UIModule`s that are registered with the application to
    create a list of base directories that the `UIModule`s are placed in.
    
    This allows you to put static files relative to the python modules that 
    contain the `UIModule`s.
    
    For example, if you have the following structure:
    
        foo/__init__.py
        foo/uimodules.py
        foo/css/bar.css
    
    and the following `UIModule` in uimodules.py is loaded into the 
    `Application`:
    
        class BarModule(UIModule):
            def css_files(self):
                return ['css/bar.css']
    
    then the `UIModuleFinder` will search inside the foo folder when trying to
    resolve the absolute url of a static file.
    
    Note: the order of search cannot be guaranteed, so use unique names for
    assets in your UIModules.
    """
    def __init__(self, modules):
        self.ui_modules = []
        self._load_ui_modules(modules)
        ui_modules = set([cls.__module__ for cls in self.ui_modules])
        self.roots = list(set([os.path.dirname(sys.modules[module].__file__) 
            for module in ui_modules]))
        
    def _load_ui_modules(self, modules):
        if type(modules) is types.ModuleType:
            self._load_ui_modules(dict((n, getattr(modules, n))
                                       for n in dir(modules)))
        elif isinstance(modules, list):
            for m in modules: self._load_ui_modules(m)
        else:
            assert isinstance(modules, dict)
            for name, cls in modules.iteritems():
                try:
                    if issubclass(cls, tornado.web.UIModule):
                        self.ui_modules.append(cls)
                except TypeError:
                    pass
        