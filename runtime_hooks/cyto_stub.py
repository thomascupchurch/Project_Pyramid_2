"""Runtime hook to guarantee dash_cytoscape/package.json exists in frozen bundles.

Some builds (interrupted COLLECT or AV interference) drop dash_cytoscape data files.
This hook runs before app code executes; we aggressively locate or synthesize the
package.json to prevent FileNotFoundError during dash_cytoscape import.
"""
import importlib.util, json, pathlib, sys, os

STUB_DATA = {"name": "dash_cytoscape", "version": "stub", "stub": True}

def _write_stub(target_dir: pathlib.Path):
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        pj = target_dir / 'package.json'
        if not pj.exists():
            pj.write_text(json.dumps(STUB_DATA))
        (target_dir / 'package.json.stub').write_text(json.dumps(STUB_DATA))
        print(f"[runtime-hook][info] stubbed dash_cytoscape at {target_dir}", file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"[runtime-hook][warn] failed writing stub: {e}", file=sys.stderr)

def _candidates():
    # 1. importlib spec parent
    try:
        spec = importlib.util.find_spec('dash_cytoscape')
        if spec and spec.origin:
            yield pathlib.Path(spec.origin).parent
    except Exception:
        pass
    # 2. Frozen _MEIPASS (PyInstaller) heuristic
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        mp = pathlib.Path(meipass) / 'dash_cytoscape'
        yield mp
    # 3. Current working directory fallback
    yield pathlib.Path.cwd() / 'dash_cytoscape'

def _ensure():
    for d in _candidates():
        try:
            pj = d / 'package.json'
            if pj.exists():
                return  # already good somewhere
        except Exception:
            continue
    # None had a package.json -> create in first writable candidate
    for d in _candidates():
        try:
            _write_stub(d)
            break
        except Exception:
            continue

_ensure()
