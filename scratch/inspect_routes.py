import sys
sys.path.insert(0, '.')
import ast
from app import main, db

db_funcs = set([d for d in dir(db) if callable(getattr(db, d)) and not d.startswith('__')])

with open('app/main.py', 'r', encoding='utf-8') as f:
    main_code = f.read()

tree = ast.parse(main_code)

func_calls = {}
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        called = []
        for subnode in ast.walk(node):
            if isinstance(subnode, ast.Call):
                if isinstance(subnode.func, ast.Name):
                    if subnode.func.id in db_funcs:
                        called.append(subnode.func.id)
                elif isinstance(subnode.func, ast.Attribute):
                    if subnode.func.attr in db_funcs:
                        called.append(subnode.func.attr)
        func_calls[node.name] = list(set(called))

routes_info = []
for route in main.app.routes:
    if hasattr(route, 'methods') and hasattr(route, 'path'):
        methods = list(route.methods - {'HEAD', 'OPTIONS'})
        if methods:
            fn_name = route.endpoint.__name__
            # Check auth by looking at endpoint dependencies or parameters
            doc = route.endpoint.__doc__ or ""
            calls = func_calls.get(fn_name, [])
            routes_info.append({
                'methods': '/'.join(methods),
                'path': route.path,
                'fn_name': fn_name,
                'calls': calls,
                'doc': doc.strip().split('\n')[0]
            })

print(f"Total API and Page endpoints: {len(routes_info)}")
for r in routes_info:
    calls_str = ', '.join(r['calls']) if r['calls'] else 'none'
    all_exist = all(c in db_funcs for c in r['calls']) if r['calls'] else True
    print(f"{r['methods']:6} | {r['path']:42} | calls: {calls_str:35} | db_exists: {all_exist}")

