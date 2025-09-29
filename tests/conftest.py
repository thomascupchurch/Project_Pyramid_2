import sys
from pathlib import Path

# Ensure project root is on sys.path so 'utils' package (with __init__.py) resolves properly.
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Optional: print once for diagnostics (won't flood because tests run once)
print(f"[conftest] sys.path[0]={sys.path[0]}")
