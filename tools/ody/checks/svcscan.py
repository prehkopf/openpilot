# ruff: noqa
import ast, sys, pathlib
ROOT = pathlib.Path(sys.argv[1]) / 'openpilot'
sys.path.insert(0, sys.argv[1])
from openpilot.cereal.services import SERVICE_LIST
SKIP = ('/tests/', '/test/', 'third_party', '/debug/', '/tools/')
bad = []
for f in ROOT.rglob('*.py'):
  if any(s in str(f) for s in SKIP): continue
  try: tree = ast.parse(f.read_text())
  except SyntaxError: continue
  for n in ast.walk(tree):
    if isinstance(n, ast.Call) and getattr(n.func, 'attr', getattr(n.func, 'id', '')) in ('SubMaster', 'PubMaster') and n.args:
      a = n.args[0]
      if isinstance(a, (ast.List, ast.Tuple)):
        for e in a.elts:
          if isinstance(e, ast.Constant) and isinstance(e.value, str) and e.value not in SERVICE_LIST:
            bad.append(f"{f.relative_to(ROOT)}:{n.lineno} {e.value}")
print(f"{len(SERVICE_LIST)} services; unknown names used: {len(bad)}")
print("\n".join(bad))
sys.exit(1 if bad else 0)
