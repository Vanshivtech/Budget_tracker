import sys
sys.path.insert(0, '.')
import ast
import os
import re

# Find all os.getenv calls across app/
env_vars = {}
for root, _, files in os.walk('app'):
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                code = file.read()
            # Regex for os.getenv
            matches = re.findall(r'os\.getenv\(\s*["\']([^"\']+)["\'](?:\s*,\s*([^)]+))?\)', code)
            for var, default in matches:
                if var not in env_vars:
                    env_vars[var] = {'files': set(), 'default': default.strip() if default else 'None'}
                env_vars[var]['files'].add(path)

with open('.env.example', 'r', encoding='utf-8') as f:
    example_text = f.read()

print(f"Total environment variables found in app/: {len(env_vars)}")
for var in sorted(env_vars.keys()):
    in_example = var in example_text
    files = ', '.join(sorted(list(env_vars[var]['files'])))
    default = env_vars[var]['default']
    print(f"VAR: {var:28} | In .env.example: {str(in_example):5} | Default: {default:30} | Files: {files}")
