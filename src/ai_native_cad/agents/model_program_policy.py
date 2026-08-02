"""Pure static policy checks for untrusted CadQuery model-program source.

This module parses source with :mod:`ast`; it never imports, bytecode-compiles,
executes, or writes the submitted program. Passing this policy is necessary but
never sufficient for execution. The separate OS-enforced sandbox capability
must also be available before CadFlow may start a model-program worker.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from typing import Any


CADQUERY_MODEL_PROGRAM_API = "cadquery_v1"
CADQUERY_MODEL_PROGRAM_ENTRYPOINT = "build_model"
MAX_MODEL_PROGRAM_SOURCE_BYTES = 65_536
MAX_MODEL_PROGRAM_AST_NODES = 4_000

MODEL_PROGRAM_SOURCE_POLICY_CODES = frozenset(
    {
        "cadquery_attribute_not_allowed",
        "cadquery_call_not_allowlisted",
        "cadquery_module_not_allowed",
        "call_not_allowlisted",
        "dangerous_call_not_allowed",
        "dynamic_call_not_allowed",
        "entrypoint_missing_or_duplicate",
        "entrypoint_return_missing",
        "entrypoint_signature_invalid",
        "function_definition_not_allowed",
        "function_signature_not_allowed",
        "import_not_allowed",
        "import_symbol_not_allowed",
        "math_attribute_not_allowed",
        "math_call_not_allowlisted",
        "method_call_not_allowlisted",
        "private_attribute_not_allowed",
        "private_name_not_allowed",
        "relative_import_not_allowed",
        "source_ast_too_large",
        "source_empty",
        "source_syntax_error",
        "source_too_large",
        "star_import_not_allowed",
        "syntax_not_allowed",
        "top_level_execution_not_allowed",
        "top_level_assignment_target_not_allowed",
    }
)

ALLOWED_MODEL_PROGRAM_IMPORTS = {
    "cadquery": frozenset(
        {
            "Compound",
            "Location",
            "Matrix",
            "Plane",
            "Shape",
            "Vector",
            "Workplane",
        }
    ),
    "math": frozenset(
        {
            "acos",
            "asin",
            "atan",
            "atan2",
            "ceil",
            "cos",
            "degrees",
            "floor",
            "hypot",
            "pi",
            "radians",
            "sin",
            "sqrt",
            "tan",
            "tau",
        }
    ),
}

ALLOWED_MATH_CALLS = ALLOWED_MODEL_PROGRAM_IMPORTS["math"] - {"pi", "tau"}

ALLOWED_MODEL_PROGRAM_BUILTIN_CALLS = frozenset(
    {
        "abs",
        "all",
        "any",
        "bool",
        "enumerate",
        "float",
        "int",
        "len",
        "list",
        "max",
        "min",
        "range",
        "round",
        "sum",
        "tuple",
        "zip",
    }
)

ALLOWED_CADQUERY_METHOD_CALLS = frozenset(
    {
        "add",
        "all",
        "arc",
        "box",
        "cboreHole",
        "center",
        "chamfer",
        "circle",
        "clean",
        "close",
        "combine",
        "cone",
        "copyWorkplane",
        "cskHole",
        "cut",
        "cutBlind",
        "cutThruAll",
        "cylinder",
        "each",
        "eachpoint",
        "edges",
        "ellipse",
        "end",
        "extrude",
        "faces",
        "fillet",
        "first",
        "hLine",
        "hLineTo",
        "hole",
        "intersect",
        "item",
        "last",
        "line",
        "lineTo",
        "loft",
        "mirror",
        "mirrorX",
        "mirrorY",
        "move",
        "moveTo",
        "offset2D",
        "polygon",
        "polyline",
        "pushPoints",
        "radiusArc",
        "rect",
        "revolve",
        "rotate",
        "rotateAboutCenter",
        "sagittaArc",
        "section",
        "shell",
        "shells",
        "slot2D",
        "solids",
        "sphere",
        "split",
        "spline",
        "sweep",
        "tag",
        "tangentArcPoint",
        "text",
        "threePointArc",
        "toPending",
        "transformGeometry",
        "transformed",
        "translate",
        "twistExtrude",
        "union",
        "vLine",
        "vLineTo",
        "vertices",
        "wedge",
        "wire",
        "wires",
        "workplane",
    }
)

FORBIDDEN_MODEL_PROGRAM_CALLS = frozenset(
    {
        "__import__",
        "breakpoint",
        "compile",
        "delattr",
        "dir",
        "eval",
        "exec",
        "getattr",
        "globals",
        "help",
        "input",
        "locals",
        "memoryview",
        "open",
        "setattr",
        "type",
        "vars",
    }
)

FORBIDDEN_CADQUERY_MODULE_ATTRIBUTES = frozenset(
    {
        "exporters",
        "importers",
        "occ_impl",
        "plugins",
        "selectors",
    }
)

_FORBIDDEN_AST_NODES = (
    ast.AsyncFunctionDef,
    ast.Await,
    ast.ClassDef,
    ast.Delete,
    ast.Global,
    ast.Lambda,
    ast.Nonlocal,
    ast.Raise,
    ast.Try,
    ast.With,
    ast.Yield,
    ast.YieldFrom,
) + ((getattr(ast, "TryStar"),) if hasattr(ast, "TryStar") else ())


@dataclass(frozen=True)
class SourcePolicyViolation:
    code: str
    line: int | None = None

    def as_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"code": self.code}
        if self.line is not None:
            value["line"] = self.line
        return value


def cadquery_model_program_policy_manifest() -> dict[str, Any]:
    """Return the versioned public contract without any execution authority."""

    return {
        "schema_version": 1,
        "api_id": CADQUERY_MODEL_PROGRAM_API,
        "cad_library": {
            "name": "CadQuery",
            "package_version": "2.7.0",
            "python_version": "3.10.12",
            "cadquery_ocp_version": "7.8.1.1.post1",
            "execution_profile": "wsl2_cadquery_v1",
            "binding_status": "internal_attestation_required",
        },
        "entrypoint": {
            "name": CADQUERY_MODEL_PROGRAM_ENTRYPOINT,
            "signature": "build_model(parameters)",
            "return_contract": "cadquery Workplane or Shape; runtime verification required",
        },
        "allowed_imports": {
            module: sorted(symbols)
            for module, symbols in ALLOWED_MODEL_PROGRAM_IMPORTS.items()
        },
        "allowed_builtin_calls": sorted(ALLOWED_MODEL_PROGRAM_BUILTIN_CALLS),
        "allowed_cadquery_method_calls": sorted(ALLOWED_CADQUERY_METHOD_CALLS),
        "forbidden_calls": sorted(FORBIDDEN_MODEL_PROGRAM_CALLS),
        "forbidden_cadquery_modules": sorted(
            FORBIDDEN_CADQUERY_MODULE_ATTRIBUTES
        ),
        "limits": {
            "source_bytes": MAX_MODEL_PROGRAM_SOURCE_BYTES,
            "ast_nodes": MAX_MODEL_PROGRAM_AST_NODES,
        },
        "authority": {
            "source_execution": False,
            "filesystem": False,
            "network": False,
            "process": False,
            "dependency_installation": False,
            "publication": False,
        },
    }


def validate_cadquery_model_program_source(source: str) -> dict[str, Any]:
    """Validate source without bytecode compilation, import, or execution."""

    if not isinstance(source, str) or not source.strip():
        return _source_result(
            source if isinstance(source, str) else "",
            violations=(SourcePolicyViolation("source_empty"),),
        )
    source_bytes = len(_source_bytes(source))
    if source_bytes > MAX_MODEL_PROGRAM_SOURCE_BYTES:
        return _source_result(
            source,
            violations=(SourcePolicyViolation("source_too_large"),),
            source_bytes=source_bytes,
        )
    try:
        tree = ast.parse(source, filename="<untrusted-model-program>", mode="exec")
    except (SyntaxError, UnicodeError, ValueError, TypeError, RecursionError):
        return _source_result(
            source,
            violations=(SourcePolicyViolation("source_syntax_error"),),
            source_bytes=source_bytes,
        )
    node_count = sum(1 for _ in ast.walk(tree))
    if node_count > MAX_MODEL_PROGRAM_AST_NODES:
        return _source_result(
            source,
            violations=(SourcePolicyViolation("source_ast_too_large"),),
            source_bytes=source_bytes,
            ast_nodes=node_count,
        )
    validator = _CadQuerySourceVisitor(tree)
    try:
        validator.validate()
    except RecursionError:
        return _source_result(
            source,
            violations=(SourcePolicyViolation("source_ast_too_large"),),
            source_bytes=source_bytes,
            ast_nodes=node_count,
        )
    return _source_result(
        source,
        violations=validator.violations,
        source_bytes=source_bytes,
        ast_nodes=node_count,
        imports=validator.imports,
    )


class _CadQuerySourceVisitor(ast.NodeVisitor):
    def __init__(self, tree: ast.Module) -> None:
        self.tree = tree
        self.violations: tuple[SourcePolicyViolation, ...] = ()
        self._violation_keys: set[tuple[str, int | None]] = set()
        self.module_aliases: dict[str, str] = {}
        self.imported_call_names: set[str] = set()
        self.function_names = {
            item.name for item in tree.body if isinstance(item, ast.FunctionDef)
        }
        self.imports: set[str] = set()

    def validate(self) -> None:
        self._validate_top_level()
        self._validate_entrypoint()
        self.visit(self.tree)

    def _add(self, code: str, node: ast.AST | None = None) -> None:
        line = getattr(node, "lineno", None) if node is not None else None
        key = (code, line)
        if key in self._violation_keys:
            return
        self._violation_keys.add(key)
        self.violations = (*self.violations, SourcePolicyViolation(code, line))

    def _validate_top_level(self) -> None:
        allowed = (
            ast.Import,
            ast.ImportFrom,
            ast.FunctionDef,
            ast.Assign,
            ast.AnnAssign,
            ast.Expr,
        )
        for item in self.tree.body:
            if not isinstance(item, allowed):
                self._add("top_level_execution_not_allowed", item)
            elif isinstance(item, ast.Expr) and not (
                isinstance(item.value, ast.Constant)
                and isinstance(item.value.value, str)
            ):
                self._add("top_level_execution_not_allowed", item)
            elif isinstance(item, ast.Assign) and not _is_static_value(item.value):
                self._add("top_level_execution_not_allowed", item)
            elif isinstance(item, ast.Assign) and not all(
                _is_static_assignment_target(target) for target in item.targets
            ):
                self._add("top_level_assignment_target_not_allowed", item)
            elif isinstance(item, ast.AnnAssign) and (
                item.value is not None and not _is_static_value(item.value)
            ):
                self._add("top_level_execution_not_allowed", item)
            elif isinstance(item, ast.AnnAssign) and not _is_static_assignment_target(
                item.target
            ):
                self._add("top_level_assignment_target_not_allowed", item)

    def _validate_entrypoint(self) -> None:
        matches = [
            item
            for item in self.tree.body
            if isinstance(item, ast.FunctionDef)
            and item.name == CADQUERY_MODEL_PROGRAM_ENTRYPOINT
        ]
        if len(matches) != 1:
            self._add("entrypoint_missing_or_duplicate")
            return
        entrypoint = matches[0]
        arguments = entrypoint.args
        valid_signature = (
            not entrypoint.decorator_list
            and len(arguments.posonlyargs) == 0
            and len(arguments.args) == 1
            and arguments.args[0].arg == "parameters"
            and not arguments.kwonlyargs
            and arguments.vararg is None
            and arguments.kwarg is None
            and not arguments.defaults
            and not arguments.kw_defaults
        )
        if not valid_signature:
            self._add("entrypoint_signature_invalid", entrypoint)
        if not _function_has_return(entrypoint):
            self._add("entrypoint_return_missing", entrypoint)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name not in ALLOWED_MODEL_PROGRAM_IMPORTS:
                self._add("import_not_allowed", node)
                continue
            bound_name = alias.asname or alias.name
            if bound_name.startswith("_"):
                self._add("private_name_not_allowed", node)
                continue
            self.module_aliases[bound_name] = alias.name
            self.imports.add(alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level != 0 or node.module not in ALLOWED_MODEL_PROGRAM_IMPORTS:
            self._add(
                "relative_import_not_allowed" if node.level else "import_not_allowed",
                node,
            )
            return
        allowed_symbols = ALLOWED_MODEL_PROGRAM_IMPORTS[node.module]
        for alias in node.names:
            if alias.name == "*":
                self._add("star_import_not_allowed", node)
                continue
            if alias.name not in allowed_symbols:
                self._add("import_symbol_not_allowed", node)
                continue
            bound_name = alias.asname or alias.name
            if bound_name.startswith("_"):
                self._add("private_name_not_allowed", node)
                continue
            if node.module == "cadquery" or alias.name in ALLOWED_MATH_CALLS:
                self.imported_call_names.add(bound_name)
            self.imports.add(f"{node.module}.{alias.name}")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name.startswith("_") or node.decorator_list:
            self._add("function_definition_not_allowed", node)
        if node.args.defaults or any(
            value is not None for value in node.args.kw_defaults
        ):
            self._add("function_signature_not_allowed", node)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id.startswith("_"):
            self._add("private_name_not_allowed", node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("_"):
            self._add("private_attribute_not_allowed", node)
        root, attributes = _attribute_chain(node)
        module = self.module_aliases.get(root) if root is not None else None
        if module == "cadquery" and attributes:
            if attributes[0] in FORBIDDEN_CADQUERY_MODULE_ATTRIBUTES:
                self._add("cadquery_module_not_allowed", node)
            elif len(attributes) == 1 and attributes[0] not in (
                ALLOWED_MODEL_PROGRAM_IMPORTS["cadquery"]
                | ALLOWED_CADQUERY_METHOD_CALLS
            ):
                self._add("cadquery_attribute_not_allowed", node)
        elif module == "math" and attributes and (
            len(attributes) != 1
            or attributes[0] not in ALLOWED_MODEL_PROGRAM_IMPORTS["math"]
        ):
            self._add("math_attribute_not_allowed", node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        function = node.func
        if isinstance(function, ast.Name):
            name = function.id
            if name in FORBIDDEN_MODEL_PROGRAM_CALLS:
                self._add("dangerous_call_not_allowed", node)
            elif name not in (
                ALLOWED_MODEL_PROGRAM_BUILTIN_CALLS
                | self.imported_call_names
                | self.function_names
            ):
                self._add("call_not_allowlisted", node)
        elif isinstance(function, ast.Attribute):
            root, attributes = _attribute_chain(function)
            module = self.module_aliases.get(root) if root is not None else None
            leaf = attributes[-1] if attributes else function.attr
            if module == "cadquery" and len(attributes) == 1:
                if leaf not in ALLOWED_MODEL_PROGRAM_IMPORTS["cadquery"]:
                    self._add("cadquery_call_not_allowlisted", node)
            elif module == "math" and len(attributes) == 1:
                if leaf not in ALLOWED_MATH_CALLS:
                    self._add("math_call_not_allowlisted", node)
            elif leaf not in ALLOWED_CADQUERY_METHOD_CALLS:
                self._add("method_call_not_allowlisted", node)
        else:
            self._add("dynamic_call_not_allowed", node)
        self.generic_visit(node)

    def generic_visit(self, node: ast.AST) -> None:
        if isinstance(node, _FORBIDDEN_AST_NODES):
            self._add("syntax_not_allowed", node)
        super().generic_visit(node)


def _attribute_chain(node: ast.Attribute) -> tuple[str | None, list[str]]:
    attributes: list[str] = []
    value: ast.AST = node
    while isinstance(value, ast.Attribute):
        attributes.append(value.attr)
        value = value.value
    attributes.reverse()
    return (value.id if isinstance(value, ast.Name) else None), attributes


def _is_static_value(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_is_static_value(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            key is not None and _is_static_value(key) and _is_static_value(value)
            for key, value in zip(node.keys, node.values)
        )
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return _is_static_value(node.operand)
    return False


def _is_static_assignment_target(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return not node.id.startswith("_")
    if isinstance(node, (ast.Tuple, ast.List)):
        return all(_is_static_assignment_target(item) for item in node.elts)
    return False


def _function_has_return(function: ast.FunctionDef) -> bool:
    pending: list[ast.AST] = list(function.body)
    while pending:
        node = pending.pop()
        if isinstance(node, ast.Return):
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        pending.extend(ast.iter_child_nodes(node))
    return False


def _source_result(
    source: str,
    *,
    violations: tuple[SourcePolicyViolation, ...],
    source_bytes: int | None = None,
    ast_nodes: int = 0,
    imports: set[str] | None = None,
) -> dict[str, Any]:
    encoded_source = _source_bytes(source)
    source_hash = hashlib.sha256(encoded_source).hexdigest()
    ordered = sorted(
        violations,
        key=lambda item: (item.line is None, item.line or 0, item.code),
    )
    codes = sorted({item.code for item in ordered})
    return {
        "valid": not ordered,
        "api_id": CADQUERY_MODEL_PROGRAM_API,
        "entrypoint": CADQUERY_MODEL_PROGRAM_ENTRYPOINT,
        "source_sha256": source_hash,
        "codes": codes,
        "violations": [item.as_dict() for item in ordered],
        "imports": sorted(imports or ()),
        "metrics": {
            "source_bytes": (
                source_bytes
                if source_bytes is not None
                else len(encoded_source)
            ),
            "ast_nodes": ast_nodes,
        },
        "executed": False,
        "side_effect_started": False,
    }


def _source_bytes(source: str) -> bytes:
    return source.encode("utf-8", errors="surrogatepass")


__all__ = [
    "ALLOWED_CADQUERY_METHOD_CALLS",
    "ALLOWED_MODEL_PROGRAM_BUILTIN_CALLS",
    "ALLOWED_MODEL_PROGRAM_IMPORTS",
    "ALLOWED_MATH_CALLS",
    "CADQUERY_MODEL_PROGRAM_API",
    "CADQUERY_MODEL_PROGRAM_ENTRYPOINT",
    "FORBIDDEN_MODEL_PROGRAM_CALLS",
    "MAX_MODEL_PROGRAM_AST_NODES",
    "MAX_MODEL_PROGRAM_SOURCE_BYTES",
    "MODEL_PROGRAM_SOURCE_POLICY_CODES",
    "cadquery_model_program_policy_manifest",
    "validate_cadquery_model_program_source",
]
