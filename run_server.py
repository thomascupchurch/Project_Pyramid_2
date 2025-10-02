"""Dedicated entry point to launch the Sign Estimation Dash server.
Ensures predictable startup semantics even if other modules import app.
"""
from datetime import datetime
import traceback
import sys

try:
    import app  # type: ignore
    if hasattr(app, 'start_server'):
        app.start_server()
    else:
        # Legacy path: emulate __main__
        import runpy
        runpy.run_module('app', run_name='__main__')
except Exception as e:
    with open('startup_error.log', 'a', encoding='utf-8') as f:
        f.write(f"[{datetime.utcnow().isoformat()}Z] FATAL during run_server: {e}\n")
        f.write(traceback.format_exc())
    print(f"[startup][fatal] {e}")
    sys.exit(1)
