"""ComfyUI registers /api-prefixed copies before original custom routes."""
import ast
import unittest
from pathlib import Path


class RefModRouteTests(unittest.TestCase):
    def test_explicit_api_routes_do_not_collide_with_page_aliases(self):
        tree = ast.parse((Path(__file__).parents[1] / "server.py").read_text(encoding="utf-8"))
        routes = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                        and isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == "routes"
                        and decorator.args and isinstance(decorator.args[0], ast.Constant)):
                    routes.add((decorator.func.attr, decorator.args[0].value))
        self.assertIn(("get", "/api/h3-refmods/records"), routes)
        aliases = {(method, "/api" + path) for method, path in routes}
        self.assertEqual(routes & aliases, set(), "A generated ComfyUI /api alias shadows an explicit API route")
