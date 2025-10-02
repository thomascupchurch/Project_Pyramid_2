"""Dedicated entry point to launch the Sign Estimation Dash server.
Ensures predictable startup semantics even if other modules import app.
"""
from datetime import datetime
import traceback
import sys

try:
    import app  # noqa: F401 (side effects start server if guarded by __main__ block)
except Exception:  # If the app file expects __main__, manually trigger logic
    # Fallback: emulate __main__ run
    try:
        # Re-import with run context manipulation
        import runpy
        runpy.run_module('app', run_name='__main__')
    except Exception as e:  # log error
        with open('startup_error.log', 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.utcnow().isoformat()}Z] FATAL during run_server fallback: {e}\n")
            f.write(traceback.format_exc())
        print(f"[startup][fatal] {e}")
        sys.exit(1)
