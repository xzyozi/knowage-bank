"""simulate_search_flow へのラッパーCLIスクリプト。"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.simulate_search_flow import run_simulation

if __name__ == "__main__":
    run_simulation()
