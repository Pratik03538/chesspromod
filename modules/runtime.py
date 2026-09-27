from __future__ import annotations

import ast
import json
from pathlib import Path

_NAMESPACE=None
BASE=Path(__file__).resolve().parent.parent
CONFIG=BASE/"config.py"
MODULES=BASE/"modules"
MANIFEST=MODULES/"manifest.json"
GUARD=MODULES/"main_guard.py"


def _compile_node(node, filename, source_text, namespace):
    flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT if False else 0
    tree=ast.parse(source_text, filename=filename, mode="exec")
    code=compile(tree, filename, "exec")
    exec(code, namespace, namespace)


def bootstrap_namespace(caller_name="main", caller_file=None):
    global _NAMESPACE
    if _NAMESPACE is not None:
        return _NAMESPACE

    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    ns={
        "__name__": caller_name,
        "__file__": str(caller_file or (BASE/"main.py")),
        "__package__": None,
        "__cached__": None,
    }

    # Load every current top-level config statement in source order.
    # This avoids stale position mappings when config.py gains new settings.
    config_text=CONFIG.read_text(encoding="utf-8")
    config_tree=ast.parse(config_text, filename=str(CONFIG))
    for node in config_tree.body:
        wrapper=ast.Module(body=[node],type_ignores=[])
        ast.fix_missing_locations(wrapper)
        exec(compile(wrapper,str(CONFIG),"exec"),ns,ns)

    # The manifest still defines the deterministic module load order, but
    # function lookup is by function name and all current functions are loaded.
    # This keeps the modular runtime valid when helper functions are added
    # without having to regenerate positional indexes.
    module_order=[]
    for item in manifest["nodes"]:
        if item["kind"] == "function":
            module=item["module"]
            if module not in module_order:
                module_order.append(module)

    for filename in module_order:
        path=MODULES/filename
        source_text=path.read_text(encoding="utf-8")
        module_tree=ast.parse(source_text, filename=str(path))

        for node in module_tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                wrapper=ast.Module(body=[node],type_ignores=[])
                ast.fix_missing_locations(wrapper)
                exec(compile(wrapper,str(path),"exec"),ns,ns)

    guard_text=GUARD.read_text(encoding="utf-8")
    guard_tree=ast.parse(guard_text, filename=str(GUARD))
    # Preserve the original __main__ guard semantics.
    exec(compile(guard_tree,str(GUARD),"exec"),ns,ns)

    _NAMESPACE=ns
    return ns


def get_namespace(caller_name="main", caller_file=None):
    return bootstrap_namespace(caller_name, caller_file)
