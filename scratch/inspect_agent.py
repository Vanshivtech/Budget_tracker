import sys
sys.path.insert(0, '.')
import inspect
from app import agent, db

db_funcs = set([d for d in dir(db) if callable(getattr(db, d)) and not d.startswith('__')])

print(f"Total tools in agent.TOOLS list: {len(agent.TOOLS)}")

for t in agent.TOOLS:
    name = t.name
    desc = t.description
    args = t.args
    # Let's inspect which db functions are referenced in the tool's function
    func = t.func if hasattr(t, 'func') else None
    called_db = []
    if func:
        source = inspect.getsource(func)
        for df in db_funcs:
            if df in source:
                called_db.append(df)
    print(f"\nTOOL: {name}")
    print(f"  Description: {desc.strip()[:100]}...")
    print(f"  Args: {list(args.keys())}")
    print(f"  DB calls: {called_db}")
    print(f"  In agent.tools: True")
