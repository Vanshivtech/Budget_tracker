import re
import sys
sys.path.insert(0, '.')
from app.main import app

# 1. Collect all backend routes
backend_routes = set()
for r in app.routes:
    if hasattr(r, 'methods') and hasattr(r, 'path'):
        methods = sorted(list(r.methods - {'HEAD', 'OPTIONS'}))
        for m in methods:
            backend_routes.add((m, r.path))

with open('frontend/app.js', encoding='utf-8') as f:
    app_js = f.read()

with open('frontend/admin.html', encoding='utf-8') as f:
    admin_html = f.read()

with open('frontend/index.html', encoding='utf-8') as f:
    index_html = f.read()

# Pattern for api(...) or fetch(...) calls
calls = []
for file_label, text in [('app.js', app_js), ('admin.html', admin_html)]:
    # Find all /api/... occurrences
    raw_matches = re.findall(r'(/api/[a-zA-Z0-9_\-\/${}\.]+)', text)
    for rm in raw_matches:
        # Strip trailing quote, backtick, query params, etc.
        clean = re.split(r"['\"`\?]", rm)[0]
        # Normalize template expressions like ${id} or ${encCat} to {param}
        norm = re.sub(r'\$\{[^}]+\}', '{param}', clean)
        calls.append((file_label, clean, norm))

print(f"Total /api/ occurrences found: {len(calls)}")
unique_calls = sorted(set((f, n) for f, c, n in calls))

print("\n--- FRONTEND API CALLS (Normalized) ---")
for f, n in unique_calls:
    print(f"[{f:10}] {n}")

# Check which backend routes are called
print("\n--- BACKEND ROUTES CALLED BY FRONTEND ---")
called_backend = set()
for m, p in sorted(backend_routes):
    norm_p = re.sub(r'\{[^}]+\}', '{param}', p)
    # Check if norm_p or p is in unique_calls
    is_called = any(n == norm_p or n == p or norm_p.startswith(n) for f, n in unique_calls)
    if is_called:
        called_backend.add((m, p))
        print(f"  CALLED: {m:6} {p}")

print("\n--- BACKEND ROUTES NOT CALLED BY FRONTEND (OR BUILT BUT UNREACHABLE) ---")
uncalled = sorted(backend_routes - called_backend)
for m, p in uncalled:
    print(f"  UNREACHABLE: {m:6} {p}")

print(f"\nSummary: {len(backend_routes)} backend endpoints, {len(called_backend)} called, {len(uncalled)} not called.")

# Check for any fetch/api in frontend that does NOT exist in backend
print("\n--- FRONTEND CALLS NOT IN BACKEND ---")
backend_norm_paths = {re.sub(r'\{[^}]+\}', '{param}', p) for m, p in backend_routes}
for f, n in unique_calls:
    if n not in backend_norm_paths:
        print(f"  UNKNOWN: [{f}] {n}")
