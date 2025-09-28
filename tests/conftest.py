import sys
from pathlib import Path

# Ensure utils directory is on path for tests
utils_path = Path(__file__).parent.parent / 'utils'
if str(utils_path) not in sys.path:
    sys.path.insert(0, str(utils_path))
