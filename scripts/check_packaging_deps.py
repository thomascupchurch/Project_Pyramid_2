import importlib
import sys

def check(modname: str):
    try:
        m = importlib.import_module(modname)
        path = getattr(m, "__file__", None)
        ver = getattr(m, "__version__", None)
        print(f"OK {modname}: path={path} version={ver}")
        return True
    except Exception as e:
        print(f"FAIL {modname}: {e}")
        return False

print(sys.executable)
ok1 = check("pefile")
ok2 = check("altgraph")
ok3 = check("altgraph.ObjectGraph")

sys.exit(0 if (ok1 and ok2 and ok3) else 1)
