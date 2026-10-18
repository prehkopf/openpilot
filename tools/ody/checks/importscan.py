# ruff: noqa
"""Static check: every `openpilot.*` / `opendbc.*` / `cereal` import resolves to a module, and every
`from X import name` names something X defines (top-level def/class/assign/import, or a submodule)."""
import ast, sys, pathlib
ROOT = pathlib.Path(sys.argv[1])            # /root/odynext
PKGS = {'openpilot': ROOT / 'openpilot', 'opendbc': ROOT / 'opendbc_repo' / 'opendbc'}
SKIP = ('/tests/', '/test/', '/third_party/', '/.venv/', 'tinygrad_repo', '/tools/', '/debug/', '/scripts/')

def mod_path(mod):
  parts = mod.split('.')
  if parts[0] not in PKGS: return None
  base = PKGS[parts[0]].joinpath(*parts[1:])
  for p in (base.with_suffix('.py'), base / '__init__.py', base.with_suffix('.pyi')):
    if p.exists(): return p
  if base.is_dir(): return base  # namespace pkg
  # compiled extension (.so / pyx)
  if list(base.parent.glob(base.name + '*.so')) or base.with_suffix('.pyx').exists(): return 'ext'
  return False

cache = {}
def names_in(p):
  if p in cache: return cache[p]
  out = set(); star = False
  if isinstance(p, pathlib.Path) and p.is_file():
    try: tree = ast.parse(p.read_text())
    except Exception: cache[p] = (None, True); return cache[p]
    for n in tree.body:
      for node in ([n] + (n.body + n.orelse if isinstance(n, (ast.If, ast.Try)) else [])
                   + ([h for hd in getattr(n, 'handlers', []) for h in hd.body])):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): out.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
          for t in (node.targets if isinstance(node, ast.Assign) else [node.target]):
            for e in ast.walk(t):
              if isinstance(e, ast.Name): out.add(e.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
          for a in node.names:
            if a.name == '*': star = True
            else: out.add((a.asname or a.name).split('.')[0])
    if '__getattr__' in out: star = True
  else: star = True
  cache[p] = (out, star); return cache[p]

bad = []
files = [f for f in (ROOT / 'openpilot').rglob('*.py') if not any(s in str(f) for s in SKIP)]
for f in files:
  try: tree = ast.parse(f.read_text())
  except SyntaxError as e: bad.append((f, f'SYNTAX {e}')); continue
  for node in ast.walk(tree):
    if isinstance(node, ast.Import):
      for a in node.names:
        if mod_path(a.name) is False: bad.append((f, f'import {a.name}: module missing'))
    elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
      mp = mod_path(node.module)
      if mp is None: continue
      if mp is False: bad.append((f, f'from {node.module}: module missing')); continue
      names, star = names_in(mp) if mp != 'ext' else (set(), True)
      if star or names is None: continue
      for a in node.names:
        if a.name == '*' or a.name in names: continue
        if isinstance(mp, pathlib.Path) and mod_path(node.module + '.' + a.name): continue
        bad.append((f, f'from {node.module} import {a.name}: name missing'))
# generated at runtime (capnp) or assigned inside a `with` block, so the AST scan can't see them
FALSE_POSITIVES = ("from openpilot.cereal import log:", "from openpilot.cereal import custom:", "from openpilot.cereal import car:",
                   "import OFFROAD_ALERTS:")
bad = [(f, m) for f, m in bad if not any(fp in m for fp in FALSE_POSITIVES)]
print(f"scanned {len(files)} files")
for f, msg in sorted(bad, key=lambda x: str(x[0])):
  print(f"{f.relative_to(ROOT)}:  {msg}")
print(f"{len(bad)} problems")
sys.exit(1 if bad else 0)
