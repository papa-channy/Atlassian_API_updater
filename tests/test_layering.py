"""Spec §4 / §21.4: import direction and no-direct-HTTP rules, checked with ast."""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = ROOT / "tools" / "atlassian_docs"
PHASE1 = ["__main__.py", "sources.py", "extractor.py", "sync.py", "storage.py"]
HTTP_MODULES = {"urllib.request", "http.client", "socket"}
OPTIONAL_VALIDATORS = {"jsonschema", "referencing"}


def _imports(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            base = "." * node.level + (node.module or "")
            yield base
            for alias in node.names:
                yield f"{base}.{alias.name}" if base else alias.name


def _py_files(directory: pathlib.Path):
    return sorted(directory.rglob("*.py")) if directory.exists() else []


class TestLayering(unittest.TestCase):
    def test_phase1_does_not_import_phase2(self):
        for name in PHASE1:
            for imp in _imports(PKG / name):
                self.assertNotIn("intelligence", imp, f"{name} imports {imp}")
                self.assertNotIn("mcp", imp.split(".")[0], f"{name} imports {imp}")

    def test_intelligence_does_not_import_mcp_or_http(self):
        for path in _py_files(PKG / "intelligence"):
            for imp in _imports(path):
                self.assertFalse(imp == "mcp" or imp.startswith("mcp.") or ".mcp" in imp,
                                 f"{path.name} imports {imp}")
                self.assertNotIn(imp, HTTP_MODULES, f"{path.name} imports {imp}")

    def test_mcp_layer_does_not_import_http(self):
        for path in _py_files(PKG / "mcp"):
            for imp in _imports(path):
                self.assertNotIn(imp, HTTP_MODULES, f"{path.name} imports {imp}")

    def test_intelligence_is_stdlib_plus_phase1_only(self):
        import sys
        allowed_prefixes = ("tools.atlassian_docs", ".")
        for path in _py_files(PKG / "intelligence"):
            for imp in _imports(path):
                top = imp.split(".")[0]
                if imp.startswith(allowed_prefixes) or top in sys.stdlib_module_names:
                    continue
                if path.name == "request_check.py" and top in OPTIONAL_VALIDATORS:
                    continue   # guarded optional import; placement checked below
                self.fail(f"{path.name} imports non-stdlib module {imp}")

    def test_optional_validator_imports_are_function_local(self):
        path = PKG / "intelligence" / "request_check.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        hits = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            else:
                continue
            if not any(n.split(".")[0] in OPTIONAL_VALIDATORS for n in names):
                continue
            hits += 1
            anc = parents.get(node)
            while anc is not None and not isinstance(anc, (ast.FunctionDef, ast.AsyncFunctionDef)):
                anc = parents.get(anc)
            self.assertIsNotNone(anc, f"module-level optional import {names} in request_check.py")
        self.assertGreater(hits, 0)

    def test_header_constants_defined_once(self):
        import ast as _ast
        hits = []
        for path in _py_files(PKG):
            tree = _ast.parse(path.read_text(encoding="utf-8"))
            for node in _ast.walk(tree):
                if isinstance(node, _ast.Assign):
                    for t in node.targets:
                        if isinstance(t, _ast.Name) and t.id in ("TRANSPORT_HEADERS", "CREDENTIAL_HEADERS"):
                            hits.append((path.name, t.id))
        self.assertEqual(sorted(hits), [("headers.py", "CREDENTIAL_HEADERS"), ("headers.py", "TRANSPORT_HEADERS")])

    def test_ranking_constants_not_in_search_py(self):
        """AC-05: inside _structural_signals every numeric literal is 0/1 (structure only) and every
        bonus/penalty/cap/table is read through the RankingPolicy argument."""
        path = PKG / "intelligence" / "search.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_structural_signals")
        nums = {n.value for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)}
        self.assertTrue(nums <= {0, 1, 0.0, 1.0}, nums)
        attrs = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
        self.assertTrue({"constants", "verb_methods", "path_noise", "product_hints"} - attrs <= {"path_noise"}, attrs)  # noise is applied at index build
        subs = {n.slice.value for n in ast.walk(fn) if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant)}
        self.assertTrue({"method_match_bonus", "method_mismatch_penalty", "path_unmatched_penalty", "path_unmatched_cap", "product_hint_bonus"} <= subs, subs)
        module_names = {n.targets[0].id for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
        self.assertFalse(any(k in module_names for k in ("VERB_METHODS", "PRODUCT_HINTS", "PATH_NOISE", "METHOD_INTENT")), module_names)
