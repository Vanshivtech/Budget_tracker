import ast
import os
import sys
sys.path.insert(0, ".")

app_dir = "app"
failed_imports = []

for fname in sorted(os.listdir(app_dir)):
    if not fname.endswith(".py"):
        continue
    fpath = os.path.join(app_dir, fname)
    with open(fpath, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=fpath)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod_name = alias.name
                try:
                    __import__(mod_name)
                except Exception as e:
                    failed_imports.append((fname, f"import {mod_name}", str(e)))
        elif isinstance(node, ast.ImportFrom):
            mod_name = node.module or ""
            # Handle relative imports
            if node.level > 0:
                mod_name = "app." + mod_name if mod_name else "app"
            for alias in node.names:
                item_name = alias.name
                try:
                    mod = __import__(mod_name, fromlist=[item_name])
                    if not hasattr(mod, item_name):
                        # Some modules might be submodules
                        try:
                            __import__(f"{mod_name}.{item_name}")
                        except Exception:
                            failed_imports.append((fname, f"from {mod_name} import {item_name}", "AttributeError: not found"))
                except Exception as e:
                    failed_imports.append((fname, f"from {mod_name} import {item_name}", str(e)))

print(f"Total import failures: {len(failed_imports)}")
for src, imp, err in failed_imports:
    print(f"  [{src}] {imp} -> {err}")
