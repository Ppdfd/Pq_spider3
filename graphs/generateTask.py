import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import numpy as np
from phase4_load_balance.generators import generate_tasks
from utils.eval_utils import GLOBAL_SEED
def main():
    seed = GLOBAL_SEED
    base_rng = np.random.default_rng(seed)
    print("Generating tasks...")
    tasks = generate_tasks(10, base_rng)
    
    print("\nGenerated Tasks:")
    print(tasks)

if __name__ == "__main__":
    main()