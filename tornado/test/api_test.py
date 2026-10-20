"""Snapshot test of Tornado's public API.

`describe_api` lists every public module-level name, class member and function
signature (parameter names, kinds and defaults; not annotations) in a stable
text format. The test compares that listing to the checked-in ``api.txt``, so
that any change to the public API, intended or not, shows up in a diff.

When a change to the API is intended, regenerate the snapshot from the root
of the repository and commit it along with the change::

    python -m tornado.test.api_test --update

Modules that can't be imported (because an optional dependency such as
``pycurl`` is missing) are skipped, so the ``-full`` tox configurations check
the whole snapshot. Some names differ between platforms (for example,
`tornado.netutil.bind_unix_socket` doesn't exist on Windows), so the
comparison only runs on Linux with CPython, where the snapshot is generated.

Names that a module imports from elsewhere are only listed if the import
has a comment saying they are re-exported, like::

    from tornado.util import TimeoutError  # re-exported for compatibility

The docs build checks that everything it documents appears in the snapshot::

    python -m tornado.test.api_test --check-docs path/to/html/objects.inv
"""

import ast
import difflib
import importlib
import inspect
import os
import platform
import sys
import textwrap
import types
import typing
import unittest
import zlib

import tornado
from tornado.test.util import TestCase


def _submodules(package: types.ModuleType) -> list[str]:
    # (mypy doesn't know about module ``__all__`` attributes.)
    return [f"{package.__name__}.{name}" for name in getattr(package, "__all__")]


# On the 6.6 branch, tornado.__all__ is missing websocket and wsgi, and
# tornado.platform has no __all__, so those modules are listed here instead
# of changing the library.
MODULES = sorted(
    ["tornado"]
    + _submodules(tornado)
    + ["tornado.websocket", "tornado.wsgi"]
    + [
        "tornado.platform.asyncio",
        "tornado.platform.caresresolver",
        "tornado.platform.twisted",
    ]
)

# Names that a module-level ``__getattr__`` creates on demand. This is the
# only one, so it's listed here instead of being found automatically.
_LAZY_NAMES = {"tornado.platform.asyncio": ["AnyThreadEventLoopPolicy"]}

SNAPSHOT_PATH = os.path.join(os.path.dirname(__file__), "api.txt")


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _assigned_names(module: types.ModuleType) -> set[str]:
    """Names assigned at the top level of a module's source.

    Used to tell constants defined in a module from ones it imports.
    Assignments inside top-level ``if`` and ``try`` blocks count.
    """
    with open(inspect.getfile(module), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    names = set()

    def visit(stmts: list[ast.stmt]) -> None:
        for stmt in stmts:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    for node in ast.walk(target):
                        if isinstance(node, ast.Name):
                            names.add(node.id)
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                names.add(stmt.target.id)
            elif isinstance(stmt, ast.If):
                visit(stmt.body)
                visit(stmt.orelse)
            elif isinstance(stmt, ast.Try):
                visit(stmt.body)
                for handler in stmt.handlers:
                    visit(handler.body)
                visit(stmt.orelse)
                visit(stmt.finalbody)

    visit(tree.body)
    return names


# Re-exports that don't have a comment saying so on the 6.6 branch.
_UNMARKED_REEXPORTS = {
    "tornado.httputil": {"responses"},
    "tornado.locale": {"LOCALE_NAMES"},
    "tornado.web": {"URLSpec"},
}


def _reexported_names(module: types.ModuleType) -> set[str]:
    """Names imported by ``from ... import`` statements that have a comment
    saying they are re-exported."""
    with open(inspect.getfile(module), encoding="utf-8") as f:
        source = f.read()
    lines = source.splitlines()
    names: set[str] = set(_UNMARKED_REEXPORTS.get(module.__name__, ()))
    for stmt in ast.parse(source).body:
        if isinstance(stmt, ast.ImportFrom):
            assert stmt.end_lineno is not None
            text = "\n".join(lines[stmt.lineno - 1 : stmt.end_lineno])
            if "re-export" in text:
                names.update(alias.asname or alias.name for alias in stmt.names)
    return names


def _instance_attributes(cls: type) -> set[str]:
    """Attributes that a class declares in its body without a value
    (including dataclass fields) or assigns to ``self`` in its methods."""
    try:
        source = textwrap.dedent(inspect.getsource(cls))
    except (OSError, TypeError):
        return set()
    class_def = ast.parse(source).body[0]
    assert isinstance(class_def, ast.ClassDef)
    names = set()
    for stmt in class_def.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            names.add(stmt.target.id)
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(stmt):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.ctx, ast.Store)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "self"
                ):
                    names.add(node.attr)
    return names


def _format_default(value: typing.Any) -> str:
    # Only simple values have reprs that are stable and meaningful.
    if value is None or isinstance(value, (bool, int, float)):
        return repr(value)
    if isinstance(value, (str, bytes)) and len(value) <= 40:
        return repr(value)
    return "..."


def _format_signature(func: typing.Callable) -> str:
    """A function's signature without annotations."""
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return "(?)"
    params = []
    for param in sig.parameters.values():
        if param.kind == param.VAR_POSITIONAL:
            text = "*" + param.name
        elif param.kind == param.VAR_KEYWORD:
            text = "**" + param.name
        else:
            text = param.name
        if param.default is not param.empty:
            text += "=" + _format_default(param.default)
        params.append((param.kind, text))
    # Render "/" and "*" markers the way Python source would.
    parts = []
    for i, (kind, text) in enumerate(params):
        prev_kind = params[i - 1][0] if i else None
        if (
            prev_kind == inspect.Parameter.POSITIONAL_ONLY
            and kind != inspect.Parameter.POSITIONAL_ONLY
        ):
            parts.append("/")
        if kind == inspect.Parameter.KEYWORD_ONLY and prev_kind not in (
            inspect.Parameter.KEYWORD_ONLY,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            parts.append("*")
        parts.append(text)
    if params and params[-1][0] == inspect.Parameter.POSITIONAL_ONLY:
        parts.append("/")
    return "(" + ", ".join(parts) + ")"


def _is_tornado_object(obj: typing.Any) -> bool:
    return getattr(obj, "__module__", "").startswith("tornado")


def _qualified_name(obj: typing.Any) -> str:
    return f"{obj.__module__}.{obj.__qualname__}"


# Functions that Python generates in some versions but not others.
_GENERATED_DUNDERS = {"__annotate__", "__annotate_func__"}


# Placeholder for attributes that only exist on instances.
_INSTANCE_ATTRIBUTE = object()


def _class_members(cls: type) -> dict[str, typing.Any]:
    """A class's own members, plus those it inherits from private bases.

    Members of public base classes are listed under those classes instead.
    """
    members: dict[str, typing.Any] = {}
    for klass in reversed(cls.__mro__):
        if klass is cls or (
            _is_tornado_object(klass) and not _is_public(klass.__name__)
        ):
            for name in _instance_attributes(klass):
                members.setdefault(name, _INSTANCE_ATTRIBUTE)
            members.update(vars(klass))
    return members


def _describe_class(prefix: str, cls: type) -> list[str]:
    bases = ", ".join(_qualified_name(b) for b in cls.__bases__ if b is not object)
    lines = [f"{prefix}: class({bases})"]
    for name, value in sorted(_class_members(cls).items()):
        is_dunder = name.startswith("__") and name.endswith("__")
        if not (_is_public(name) or is_dunder) or name in _GENERATED_DUNDERS:
            continue
        # Only functions are listed among dunder names; the attributes
        # (``__dict__``, ``__static_attributes__``, etc) vary by Python
        # version. Functions that typing and other libraries add to classes
        # are skipped too.
        if isinstance(value, (classmethod, staticmethod)):
            if _is_tornado_object(value.__func__):
                kind = type(value).__name__
                sig = _format_signature(value.__func__)
                lines.append(f"{prefix}.{name}: {kind}{sig}")
        elif inspect.isfunction(value):
            if _is_tornado_object(value):
                lines.append(f"{prefix}.{name}: method{_format_signature(value)}")
        elif is_dunder:
            continue
        elif isinstance(value, property):
            lines.append(f"{prefix}.{name}: property")
        elif inspect.isclass(value) and _is_tornado_object(value):
            lines.extend(_describe_class(f"{prefix}.{name}", value))
        else:
            lines.append(f"{prefix}.{name}: attribute")
    return lines


def describe_module(modname: str) -> list[str]:
    module = importlib.import_module(modname)
    assigned = _assigned_names(module)
    reexported = _reexported_names(module)
    lines = [
        f"{modname}.{name}: lazy attribute" for name in _LAZY_NAMES.get(modname, [])
    ]
    for name, value in sorted(vars(module).items()):
        if not _is_public(name):
            continue
        if isinstance(value, types.ModuleType) and name not in assigned:
            # An import, not part of this module's API. (A name that is
            # assigned is listed below even if it holds a module, like
            # ``colorama`` in `tornado.log`, which is None when colorama
            # isn't installed.)
            continue
        prefix = f"{modname}.{name}"
        defined_here = (
            getattr(value, "__module__", None) == modname
            and getattr(value, "__name__", None) == name
        )
        if inspect.isclass(value) and defined_here:
            lines.extend(_describe_class(prefix, value))
        elif inspect.isfunction(value) and defined_here:
            lines.append(f"{prefix}: function{_format_signature(value)}")
        elif name in assigned:
            if inspect.isclass(value) or inspect.isfunction(value):
                lines.append(f"{prefix}: alias of {_qualified_name(value)}")
            else:
                lines.append(f"{prefix}: data")
        elif name in reexported:
            if inspect.isclass(value) or inspect.isfunction(value):
                lines.append(f"{prefix}: import of {_qualified_name(value)}")
            else:
                lines.append(f"{prefix}: data")
    return lines


def describe_api(modules: list[str] = MODULES) -> dict[str, list[str]]:
    """Returns the API listing for each module that can be imported."""
    result = {}
    for modname in modules:
        try:
            result[modname] = describe_module(modname)
        except ImportError:
            continue
    return result


def format_snapshot(api: dict[str, list[str]]) -> str:
    return "".join(
        f"[{modname}]\n" + "".join(line + "\n" for line in lines) + "\n"
        for modname, lines in api.items()
    )


def parse_snapshot(text: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("[") and line.endswith("]"):
            lines = result.setdefault(line[1:-1], [])
        elif line:
            lines.append(line)
    return result


class APISnapshotTest(TestCase):
    @unittest.skipUnless(
        sys.platform.startswith("linux")
        and platform.python_implementation() == "CPython",
        "API snapshot is generated on linux with CPython",
    )
    def test_api_snapshot(self):
        with open(SNAPSHOT_PATH, encoding="utf-8") as f:
            snapshot = parse_snapshot(f.read())
        self.assertEqual(list(snapshot), MODULES, "snapshot is out of date")
        api = describe_api()
        diff = "\n".join(
            difflib.unified_diff(
                format_snapshot({m: snapshot[m] for m in api}).splitlines(),
                format_snapshot(api).splitlines(),
                "api.txt",
                "current",
                lineterm="",
                n=0,
            )
        )
        if diff:
            self.fail(
                "Public API changed. If this is intended, run "
                "`python -m tornado.test.api_test --update` "
                "and commit the result.\n" + diff
            )


def _read_inventory(path: str) -> dict[str, str]:
    """Reads a Sphinx ``objects.inv`` file, returning the Python objects it
    lists and their roles (``py:class``, ``py:method``, etc)."""
    with open(path, "rb") as f:
        for _ in range(4):
            f.readline()  # Header lines.
        data = zlib.decompress(f.read()).decode("utf-8")
    objects = {}
    for line in data.splitlines():
        # Each line is "name domain:role priority uri display-name".
        name, role = line.split()[:2]
        if role.startswith("py:"):
            objects[name] = role
    return objects


def check_docs(inventory_path: str) -> list[str]:
    """Returns the public names documented in the inventory that are missing
    from the snapshot."""
    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        snapshot = parse_snapshot(f.read())
    entries = {}
    for lines in snapshot.values():
        for line in lines:
            name, _, desc = line.partition(": ")
            entries[name] = desc

    def bases(name: str) -> list[str]:
        desc = entries.get(name, "")
        if not desc.startswith("class("):
            return []
        return [b for b in desc[len("class(") : -1].split(", ") if b]

    def listed(name: str) -> bool:
        if name in entries:
            return True
        # Members inherited from public base classes are listed there.
        owner, _, member = name.rpartition(".")
        return any(listed(f"{base}.{member}") for base in bases(owner))

    missing = []
    for name, role in sorted(_read_inventory(inventory_path).items()):
        parts = name.split(".")
        if parts[0] != "tornado" or any(
            p.startswith("_") and not p.endswith("__") for p in parts
        ):
            continue
        if role == "py:module":
            if name not in snapshot:
                missing.append(name)
        elif not listed(name):
            missing.append(name)
    return missing


def main() -> None:
    if sys.argv[1:2] == ["--check-docs"]:
        missing = check_docs(sys.argv[2])
        if missing:
            sys.exit(
                "Documented but missing from tornado/test/api.txt "
                "(see tornado/test/api_test.py):\n  " + "\n  ".join(missing)
            )
        return
    if sys.argv[1:] != ["--update"]:
        unittest.main()
        return
    api = describe_api()
    unimported = set(MODULES) - set(api)
    if unimported:
        sys.exit(f"Can't import {sorted(unimported)}; install the -full dependencies")
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        f.write(format_snapshot(api))
    print(f"Wrote {SNAPSHOT_PATH}")


if __name__ == "__main__":
    main()
