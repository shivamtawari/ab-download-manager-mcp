import sys
from pathlib import Path

src_dir = (Path(__file__).parent.parent / 'src').resolve()
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
