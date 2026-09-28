#!/usr/bin/env python3
"""Mechanically move a LabelingWidget method into a module-level function.

Split batch 5/7 proved the recipe by hand: analyse the method's free
variables, rewrite ``self`` as a ``widget`` parameter, move the body to a
module-level function, leave a thin delegating stub in the class, and
byte-compare the result.  Doing that by hand is slow and every batch risks
a slip, so this script mechanises it.  What it does per method:

* parses the method with ``ast`` and refuses anything it cannot move
  safely (``property``/``staticmethod``, ``super()``, ``global``);
* reports the self-attributes, self-methods, and external names the body
  needs -- the free-variable analysis that used to be eyeballed;
* rewrites the body textually (formatting, comments and line numbers
  preserved) with ``self`` -> ``widget``, skipping string literals;
* leaves a stub in the class so call sites, signal wiring and tests stay,
  in the house style of ``attributes_controller``:
      def update_attributes(self, shape_index):
          "Delegates to attributes_controller (wiring and tests stay)."
          attributes_controller.update_attributes(self, shape_index)
* byte-compares: the moved function's ``co_code`` must equal the
  original's instruction for instruction (LOAD_FAST addresses by slot
  index, so renaming the first parameter does not change the bytecode);
* auto-copies the import lines the moved body needs from the source
  module, and flags ``tr()`` calls -- runtime context survives the move
  (``widget.tr()`` resolves through the instance), but pylupdate6 will
  not see them, which is the known i18n debt.

The moved function lands as ``<module>.<name>(widget, ...)`` and is
imported into the source module the way ``attributes_controller`` is.

Usage
-----
    python scripts/extract_method.py \\
        --file anylabeling/views/labeling/label_widget.py \\
        --method toggle_shapes_visibility \\
        --target anylabeling/views/labeling/utils/panel_visibility.py \\
        --dry-run          # report + diff, writes nothing
    python scripts/extract_method.py ... --apply   # write both files

Run the test suite after every apply; the script proves instruction
equivalence, not behaviour.
"""

from __future__ import annotations

import argparse
import ast
import builtins
import difflib
import re
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

STUB_DOCSTRING = "Delegates to {module} (wiring and tests stay)."

#: These decorators change what the name *means*; a stub that forwards
#: would not forward the semantics.
BLOCKING_DECORATORS = {"property", "staticmethod", "classmethod"}


class Refuse(Exception):
    """The method cannot be moved safely; the message says why."""


def _find_method(tree, class_name, method_name):
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for child in node.body:
            if (
                isinstance(child, ast.FunctionDef)
                and child.name == method_name
            ):
                return child
    raise Refuse(f"{class_name}.{method_name} not found")


def _guard(method, class_name):
    body = [
        node
        for node in method.body
        if not (
            isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
        )
    ]
    if len(body) == 1 and isinstance(body[0], ast.Expr):
        call = body[0].value
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.args
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id == "self"
        ):
            raise Refuse(
                f"{class_name}.{method.name} is already a delegation "
                "stub -- it was moved before; do not re-extract it"
            )
    for dec in method.decorator_list:
        name = dec.id if isinstance(dec, ast.Name) else None
        if name in BLOCKING_DECORATORS:
            raise Refuse(f"cannot move a @{name} method")
    if method.decorator_list:
        print("  note: decorators stay on the stub")
    for node in ast.walk(method):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "super"
        ):
            raise Refuse("super() call -- decide the MRO story first")
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            raise Refuse(f"{type(node).__name__} statement in body")


def _param_names(node):
    if not isinstance(
        node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
    ):
        return []
    a = node.args
    names = [p.arg for p in a.posonlyargs + a.args + a.kwonlyargs]
    for extra in (a.vararg, a.kwarg):
        if extra:
            names.append(extra.arg)
    return names


def _module_import_names(module_tree):
    bound = set()
    for node in module_tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound.add(alias.asname or alias.name)
    return bound


def _analyze(method, module_tree):  # noqa: C901 -- binding forms
    """Free-variable report: what the body reaches beyond its locals."""
    locals_ = set(_param_names(method))
    for node in ast.walk(method):
        if isinstance(node, ast.Name) and isinstance(
            node.ctx, (ast.Store, ast.Del)
        ):
            locals_.add(node.id)
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
        ):
            locals_.update(_param_names(node))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # The nested def's own name is a local binding too -- missing
            # it made every nested helper look like an unresolved global.
            locals_.add(node.name)
        if isinstance(node, ast.comprehension):
            for t in ast.walk(node.target):
                if isinstance(t, ast.Name):
                    locals_.add(t.id)
        if isinstance(node, ast.ExceptHandler) and node.name:
            locals_.add(node.name)
        if isinstance(node, ast.withitem) and node.optional_vars:
            for t in ast.walk(node.optional_vars):
                if isinstance(t, ast.Name):
                    locals_.add(t.id)

    self_attrs = set()
    self_methods = set()
    plain_names = set()
    tr_calls = 0
    for node in ast.walk(method):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr == "tr":
                    tr_calls += 1
                if (
                    isinstance(func.value, ast.Name)
                    and func.value.id == "self"
                ):
                    self_methods.add(func.attr)
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
        ):
            self_attrs.add(node.attr)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            plain_names.add(node.id)

    module_imports = _module_import_names(module_tree)
    external = sorted(
        n
        for n in plain_names
        if n not in locals_
        and n not in self_attrs
        and n not in builtins.__dict__
        and n not in module_imports
    )
    imported = sorted(
        n for n in plain_names if n in module_imports and n not in locals_
    )
    return {
        "params": _param_names(method),
        "self_attrs": sorted(self_attrs),
        "self_methods": sorted(self_methods),
        "external": external,
        "imported": imported,
        "tr_calls": tr_calls,
    }


def _line_span(node):
    start = min([node.lineno] + [d.lineno for d in node.decorator_list])
    return start, node.end_lineno


def _string_offset_ranges(method, src):
    """Character ranges of string literals in the method text.

    ast col_offset/end_col_offset are UTF-8 *byte* offsets, not character
    offsets -- a column past a CJK string literal is three bytes further
    than it looks.  Converting with character-length accumulation made
    every range after a Chinese tr() string drift right, far enough to
    swallow a real ``self``.  Each line's byte columns are converted
    with a decode round-trip instead.
    """
    char_offsets = {1: 0}
    total = 0
    texts = {}
    for i, line in enumerate(src.splitlines(keepends=True), start=1):
        texts[i] = line
        char_offsets[i] = total
        total += len(line)

    def to_char(lineno, byte_col):
        text = texts[lineno]
        return char_offsets[lineno] + len(
            text.encode("utf-8")[:byte_col].decode("utf-8")
        )

    ranges = []
    for node in ast.walk(method):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            start = to_char(node.lineno, node.col_offset)
            end = to_char(node.end_lineno, node.end_col_offset)
            ranges.append((start, end))
    return ranges


def _rewrite_body(text, skip_ranges):
    """self -> widget outside string literals, formatting preserved."""
    pattern = re.compile(r"\bself\b")

    def skipped(pos):
        return any(s <= pos < e for s, e in skip_ranges)

    out = []
    last = 0
    for m in pattern.finditer(text):
        if skipped(m.start()):
            continue
        out.append(text[last : m.start()])
        out.append("widget")
        last = m.end()
    out.append(text[last:])
    return "".join(out)


def _has_return_value(method):
    for node in ast.walk(method):
        if isinstance(node, ast.Return) and node.value is not None:
            return True
    return False


def _call_args(method):
    a = method.args
    parts = ["self"] + [p.arg for p in a.posonlyargs + a.args[1:]]
    parts += [f"{p.arg}={p.arg}" for p in a.kwonlyargs]
    if a.vararg:
        parts.append(f"*{a.vararg.arg}")
    if a.kwarg:
        parts.append(f"**{a.kwarg.arg}")
    return ", ".join(parts)


def _stub_source(method, module_name):
    """The class-side stub, signature preserved via ast.unparse."""
    signature = ast.unparse(method).split("\n")[0]
    prefix = "def " + method.name + "("
    if not signature.startswith(prefix):
        raise Refuse(f"unexpected signature: {signature!r}")
    tail = signature[len(prefix) :]
    tail = re.sub(r"^self,?\s*", "", tail, count=1)
    if not tail.startswith(")"):
        tail = "self, " + tail
    else:
        tail = "self" + tail
    returns = "return " if _has_return_value(method) else ""
    return "\n".join(
        [
            f"    {prefix}{tail}",
            '        """' + STUB_DOCSTRING.format(module=module_name) + '"""',
            f"        {returns}{module_name}.{method.name}"
            f"({_call_args(method)})",
        ]
    )


def _needed_import_lines(
    imported_names, module_tree, src_text, target_module, depth
):
    """Whole import statements that bind names the moved body needs.

    Copied from the module tree, not from lines: a parenthesised
    multi-line import is one statement and must survive as one.  A
    relative import gains ``depth`` dots because the target lives that
    many levels deeper in the package tree (``from .logger import
    logger`` pasted one level deeper must become ``from ..logger ...``,
    otherwise it resolves to a module that does not exist).  Statements
    that mention the target module itself are skipped: the body now
    lives *in* it, so those names are module locals.
    """
    wanted = set(imported_names)
    lines = []
    for node in module_tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        segment = ast.get_source_segment(src_text, node)
        if segment is None or target_module in segment:
            continue
        bound = _module_import_names(ast.Module(body=[node], type_ignores=[]))
        if not (wanted & bound):
            continue
        if isinstance(node, ast.ImportFrom) and node.level > 0:
            node = ast.ImportFrom(
                module=node.module,
                names=node.names,
                level=node.level + depth,
            )
        lines.append(ast.unparse(node))
    return sorted(set(lines))


def _co_code_map(code):
    out = {code.co_name: code.co_code}
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            out.update(_co_code_map(const))
    return out


def _byte_compare(old_src, new_src):
    old_fn = next(
        c
        for c in compile(old_src, "<old>", "exec").co_consts
        if isinstance(c, types.CodeType)
    )
    new_fn = next(
        c
        for c in compile(new_src, "<new>", "exec").co_consts
        if isinstance(c, types.CodeType)
    )
    old_map = _co_code_map(old_fn)
    new_map = _co_code_map(new_fn)
    if old_map != new_map:
        missing = sorted(set(old_map) - set(new_map))
        extra = sorted(set(new_map) - set(old_map))
        changed = sorted(
            name
            for name in set(old_map) & set(new_map)
            if old_map[name] != new_map[name]
        )
        raise Refuse(
            "byte-compare failed: missing=%s extra=%s changed=%s"
            % (missing, extra, changed)
        )


def _relative_import_line(src_path, target_path, module_name):
    """``from .utils import panel_visibility`` style, like the house does
    for ``from .widgets import attributes_controller``."""
    try:
        rel = target_path.relative_to(src_path.parent)
    except ValueError:
        raise SystemExit(
            "--target must live under the source file's package tree"
        ) from None
    depth = len(rel.parts) - 1  # directories below the source's package
    if depth == 0:
        return f"from .{module_name} import {module_name}"
    path = ".".join(rel.parts[:-1])
    return f"from .{path} import {module_name}"


def _insert_import(src, import_line):
    """Insert after the last single-line relative import -- never inside
    a parenthesised multi-line one."""
    lines = src.splitlines(keepends=True)
    anchor = None
    for i, line in enumerate(lines[:200]):
        if not re.match(r"^from \.", line):
            continue
        if line.count("(") > line.count(")"):
            continue  # multi-line import: not a safe anchor
        anchor = i
    if anchor is None:
        for i, line in enumerate(lines[:200]):
            if re.match(r"^(import |from )", line):
                anchor = i
    if anchor is None:
        lines.insert(0, import_line + "\n")
    else:
        lines.insert(anchor + 1, import_line + "\n")
    return "".join(lines)


def _target_module_text(existing, doc, import_lines, func_text):
    """New file from scratch, or ``func_text`` appended to ``existing``."""
    if existing is None:
        parts = ['"""' + doc + '"""', ""]
        parts += import_lines + [""] if import_lines else []
        parts += [func_text, ""]
        return "\n".join(parts)

    lines = existing.splitlines(keepends=True)
    present = {line.strip() for line in lines}
    bound = set()
    try:
        for node in ast.parse(existing).body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                bound |= _module_import_names(
                    ast.Module(body=[node], type_ignores=[])
                )
    except SyntaxError:
        pass
    for imp in import_lines:
        # Line-exact, not substring: "import os" must not be considered
        # present just because "import os.path as osp" is (a real bug
        # that left os.listdir calling an undefined name).
        if imp.strip() in present:
            continue
        # Bound-name exact: the existing statement may be the same
        # import in a different shape (black split the parens after an
        # earlier batch), where string comparison double-inserts it and
        # every name in it becomes an F811 redefinition.
        try:
            imp_bound = _module_import_names(
                ast.Module(body=[ast.parse(imp)], type_ignores=[])
            )
        except SyntaxError:
            imp_bound = set()
        if imp_bound and imp_bound <= bound:
            continue
        at = 0
        for i, line in enumerate(lines):
            if line.strip().startswith(("import ", "from ")):
                at = i + 1
                break
        lines.insert(at, imp + "\n")
        bound |= imp_bound
    result = "".join(lines)
    if not result.endswith("\n"):
        result += "\n"
    return result + "\n\n" + func_text + "\n"


def _process_method(
    method_name,
    args,
    src,
    tree,
    class_name,
    target_path,
    target_acc,
    translate_class=None,
):
    method = _find_method(tree, class_name, method_name)
    _guard(method, class_name)
    report = _analyze(method, tree)
    print(f"\n=== {class_name}.{method_name} ===")
    print(f"  self attrs : {report['self_attrs']}")
    print(f"  self calls : {report['self_methods']} (stub chain, fine)")
    print(f"  imports    : {report['imported']}")
    print(
        f"  unresolved : {report['external']} "
        "<-- must be empty or module-level in the target"
    )
    print(
        f"  tr() calls : {report['tr_calls']} "
        "(runtime ok, pylupdate6 blind)"
    )
    if report["external"]:
        raise SystemExit(
            f"unresolved names {report['external']}: move their "
            "definitions first or extend the import copy logic"
        )

    start, end = _line_span(method)
    src_lines = src.splitlines()
    block = "\n".join(src_lines[start - 1 : end])
    dedented = "\n".join(
        line[4:] if line.startswith("    ") else line
        for line in block.splitlines()
    )
    # String ranges must be computed against the *dedented* text the
    # rewrite runs on: offsets taken from the indented original drift by
    # 4 chars per line, and past a docstring or two they start eating
    # real ``self`` references (the byte-compare will catch it -- this
    # was a real bug the guard refused).
    dedented_fn = ast.parse(dedented).body[0]
    skip_ranges = _string_offset_ranges(dedented_fn, dedented)
    new_func = _rewrite_body(dedented, skip_ranges)
    _byte_compare(dedented, new_func)
    tr_imports = []
    if translate_class:
        # Equivalent at runtime (instance tr() resolves through the
        # widget's own class), but pylupdate6 can only see explicit
        # translate() calls, so moved strings stop silently dropping out
        # of the .ts catalog.  Runs after the byte-compare on purpose:
        # it is a behaviour-equivalent rename of the lookup, not a move.
        marker = 'QCoreApplication.translate("%s", ' % translate_class
        if "widget.tr(" in new_func:
            new_func = new_func.replace("widget.tr(", marker)
            # One bare import, not two: if an auto-copied line
            # already binds QCoreApplication this would be an F811.
            tr_imports.append("from PyQt6.QtCore import QCoreApplication")
    print("  byte-compare: co_code identical")

    module_name = target_path.stem
    depth = len(target_path.relative_to(args.file_path.parent).parts) - 1
    import_lines = _needed_import_lines(
        report["imported"], tree, src, module_name, depth
    )
    bound_by_copies = set()
    for line in import_lines:
        if line.lstrip().startswith("from ") and "QCoreApplication" in line:
            bound_by_copies.add(line)
    import_lines += [
        i for i in tr_imports if i not in import_lines and not bound_by_copies
    ]
    doc = args.doc or (
        f"Methods moved out of {class_name} by " "scripts/extract_method.py."
    )
    target_text = _target_module_text(target_acc, doc, import_lines, new_func)
    stub = _stub_source(method, module_name)
    new_src_lines = (
        src_lines[: start - 1] + stub.splitlines() + src_lines[end:]
    )
    new_src = "\n".join(new_src_lines)
    if src.endswith("\n"):
        new_src += "\n"
    import_line = _relative_import_line(
        args.file_path, target_path, module_name
    )
    if import_line not in new_src:
        new_src = _insert_import(new_src, import_line)

    compile(new_src, str(args.file_path), "exec")
    compile(target_text, str(target_path), "exec")
    print(f"  both files compile; stub -> {module_name}.{method_name}")

    if args.dry_run:
        for line in difflib.unified_diff(
            src.splitlines(),
            new_src.splitlines(),
            fromfile=str(args.file_path),
            tofile=str(args.file_path),
            lineterm="",
            n=1,
        ):
            print(line)
    return new_src, target_text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", required=True, help="source module path")
    ap.add_argument("--class-name", default=None, help="default: first class")
    ap.add_argument(
        "--method", required=True, action="append", help="repeatable"
    )
    ap.add_argument("--target", required=True, help="destination module path")
    ap.add_argument("--doc", default=None, help="target module docstring")
    ap.add_argument(
        "--translate-class",
        default=None,
        metavar="CLASS",
        help="rewrite widget.tr(...) as QCoreApplication.translate"
        "('CLASS', ...) so pylupdate6 keeps the strings",
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="report and diff, no writes"
    )
    ap.add_argument("--apply", action="store_true", help="write both files")
    args = ap.parse_args(argv)

    src_path = REPO_ROOT / args.file
    target_path = REPO_ROOT / args.target
    args.file_path = src_path
    src = src_path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    class_name = args.class_name
    if class_name is None:
        class_name = next(
            n.name for n in tree.body if isinstance(n, ast.ClassDef)
        )

    target_acc = None
    if target_path.exists():
        target_acc = target_path.read_text(encoding="utf-8")
    for method_name in args.method:
        src, target_acc = _process_method(
            method_name,
            args,
            src,
            tree,
            class_name,
            target_path,
            target_acc,
            translate_class=args.translate_class,
        )
        tree = ast.parse(src)
    if args.apply:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(target_acc, encoding="utf-8")
        src_path.write_text(src, encoding="utf-8")
        print(f"\nwrote {target_path} and {src_path}")

    if not (args.dry_run or args.apply):
        print("\nnothing written: pass --dry-run to preview or --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
