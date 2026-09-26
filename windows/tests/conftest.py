import sys
from pathlib import Path

# Make the app modules importable (they live one directory up, not in a package).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
