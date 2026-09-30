"""Spec §4 / §21.4: import direction and no-direct-HTTP rules, checked with ast."""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = ROOT / "tools" / "atlassian_docs"
PHASE1 = ["__main__.py", "sources.py", "extractor.py", "sync.py", "storage.py"]
HTTP_MODULES = {"urllib.request", "http.client", "socket"}


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
                self.fail(f"{path.name} imports non-stdlib module {imp}")

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
