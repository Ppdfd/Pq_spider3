#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from utils.eval_utils import set_global_seed, ensure_dirs, configure_matplotlib, GLOBAL_SEED
from graphs.graph8 import graph8_recovery_latency
from graphs.graph9 import graph9_task_completion

def main():
    rng = set_global_seed(GLOBAL_SEED)
    ensure_dirs()
    configure_matplotlib()

    print("Generating Graph 8...")
    graph8_recovery_latency(rng)
    print("Graph 8 generated successfully.")

    print("Generating Graph 9...")
    graph9_task_completion(rng)
    print("Graph 9 generated successfully.")

if __name__ == "__main__":
    main()
