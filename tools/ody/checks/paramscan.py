# ruff: noqa
import ast, re, sys, pathlib
ROOT = pathlib.Path(sys.argv[1]) / 'openpilot'
keys = set()
for h in ROOT.rglob('*params_keys*.h'):
  keys |= set(re.findall(r'\{"([A-Za-z0-9_]+)"\s*,', h.read_text()))
METHODS = {'get', 'put', 'get_bool', 'put_bool', 'put_nonblocking', 'put_bool_nonblocking', 'remove', 'check_key',
           'get_default_value', 'get_type', 'get_key_flag'}
SKIP = ('/tests/', '/test/', 'third_party', '/debug/')
uses = {}
for f in ROOT.rglob('*.py'):
  if any(s in str(f) for s in SKIP): continue
  try: tree = ast.parse(f.read_text())
  except SyntaxError: continue
  for n in ast.walk(tree):
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in METHODS and n.args \
       and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
      recv = ast.unparse(n.func.value)
      if 'param' not in recv.lower(): continue
      k = n.args[0].value
      if re.fullmatch(r'[A-Z][A-Za-z0-9_]+', k):
        uses.setdefault(k, []).append(f"{f.relative_to(ROOT)}:{n.lineno}")
print(f"{len(keys)} registered keys, {len(uses)} literal keys used")
missing = {k: v for k, v in uses.items() if k not in keys}
for k, v in sorted(missing.items()):
  print(f"UNREGISTERED {k}: " + ", ".join(v[:4]))
print(f"{len(missing)} unregistered")
sys.exit(1 if missing else 0)
