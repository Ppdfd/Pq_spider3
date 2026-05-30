# phase4_load_balance — Load Balancing Simulation Engine
#
# Contains the discrete-event simulator for Spider hierarchical scheduling:
#   params.py       — SIMULATION_PARAMS (cited constants)
#   models.py       — WorkloadTask, FogNode, Enclave dataclasses
#   generators.py   — Task/node/enclave population generators
#   inter_node.py   — Level 1: inter-node scheduling (Spider, Ref[22/37/39])
#   intra_node.py   — Level 2: intra-node enclave scheduling (Spider, RR, LQ)
#   mfn_election.py — Master Fog Node election (Sec IV, Eq 112-116)
#   failure_detection.py — Group-based failure detection (Sec V, Eq 117-125)
#   optee_bench/    — OP-TEE QEMU measurement data and loader

# Re-export public symbols for convenience
from .params import SIMULATION_PARAMS
from .models import (
    WorkloadTask, FogNode, Enclave,
    clone_nodes, clone_enclaves,
)
from .generators import (
    generate_tasks, generate_nodes, generate_enclaves,
)
from .inter_node import (
    epc_pressure_penalty,
    choose_node, execute_task, simulate_load_balancing,
)
from .intra_node import (
    choose_enclave, execute_on_enclave,
    simulate_intra_node,
)
