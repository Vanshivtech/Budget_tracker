# inspect views and navigation
with open('frontend/index.html', encoding='utf-8') as f:
    lines = f.readlines()

print("--- Views ---")
for i, line in enumerate(lines, 1):
    if 'id="view-' in line or 'class="view' in line or 'class="nav' in line or 'nav-' in line or 'bottom' in line:
        print(f"{i}: {line.strip()[:120]}")
