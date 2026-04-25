import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from evaluation.spiderpp_full_evaluation import graph7_intra_enclave, set_global_seed, GLOBAL_SEED

rng = set_global_seed(GLOBAL_SEED)
print("Running Graph 7 simulation only...")
graph7_intra_enclave(rng, reps=1)
print("Finished Graph 7")
