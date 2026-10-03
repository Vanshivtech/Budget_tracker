import os
import sys
sys.path.insert(0, '.')
import py_compile
import ast
import re

app_dir = 'app'
py_files = [os.path.join(app_dir, f) for f in os.listdir(app_dir) if f.endswith('.py')]

print("=== 1. PY_COMPILE TEST ===")
for pf in sorted(py_files):
    try:
        py_compile.compile(pf, doraise=True)
        print(f"[OK] {pf}")
    except Exception as e:
        print(f"[FAIL] {pf}: {e}")

print("\n=== 2. IMPORT CHECKS ===")
for pf in sorted(py_files):
    mod_name = pf.replace('\\', '.').replace('/', '.').replace('.py', '')
    try:
        __import__(mod_name)
        print(f"[IMPORT OK] {mod_name}")
    except Exception as e:
        print(f"[IMPORT FAIL] {mod_name}: {e}")

print("\n=== 3. TODOS, FIXMES, BUGS ===")
for pf in sorted(py_files):
    with open(pf, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    for idx, line in enumerate(lines):
        if any(w in line.upper() for w in ['TODO', 'FIXME', 'BUG', 'HACK']):
            print(f"{pf}:{idx+1}: {line.strip()}")

print("\n=== 4. BARE EXCEPT CHECKS ===")
for pf in sorted(py_files):
    with open(pf, 'r', encoding='utf-8') as f:
        code = f.read()
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                # Bare except:
                body_strs = [ast.dump(b) for b in node.body]
                print(f"[BARE EXCEPT] {pf}:{node.lineno} -> handlers: {len(node.body)} statements")
            elif isinstance(node.type, ast.Name) and node.type.id == 'Exception' and node.name is None:
                # except Exception: without binding as e
                # Check if pass or return None without logging
                is_pass = any(isinstance(b, ast.Pass) for b in node.body)
                if is_pass:
                    print(f"[SILENT EXCEPT PASS] {pf}:{node.lineno}")
