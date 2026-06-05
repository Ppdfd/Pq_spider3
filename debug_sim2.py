"""
Diagnostic: Compare what happens when Spider vs baseline picks the same task.
Key question: does picking a DIFFERENT node actually change the latency?
"""
import numpy as np
import sys
sys.path.insert(0, '.')
from utils.eval_utils import GLOBAL_SEED
from phase4_load_balance.inter_node import execute_task, epc_pressure_penalty
from phase4_load_balance.generators import generate_tasks, generate_nodes
from phase4_load_balance.models import clone_nodes, FogNode, WorkloadTask
from phase4_load_balance.params import SIMULATION_PARAMS

# Create two nodes: one fast+small EPC, one slow+large EPC
fast_node = FogNode(node_id=0, tee_rate=3.5, ree_rate=3.5, network_ms=10.0,
                    epc_total_mb=90, trust=0.95, energy_factor=1.0)
slow_node = FogNode(node_id=1, tee_rate=0.8, ree_rate=0.8, network_ms=10.0,
                    epc_total_mb=512, trust=0.95, energy_factor=1.0)

task = WorkloadTask(arrival_ms=100.0, records=10, attrs=20, policy_depth=3,
                    payload_kb=20.0, risk=0.3, deadline_ms=300, tee_work=30.0,
                    ree_work=18.0, epc_req_mb=50.0)

rng1 = np.random.default_rng(42)
rng2 = np.random.default_rng(42)

lat_fast = execute_task(fast_node, task, rng1)
lat_slow = execute_task(slow_node, task, rng2)

print(f"=== SINGLE TASK COMPARISON ===")
print(f"Fast node (3.5/3.5, 90MB EPC): {lat_fast:.2f}ms")
print(f"Slow node (0.8/0.8, 512MB EPC): {lat_slow:.2f}ms")
print(f"Difference: {lat_slow - lat_fast:.2f}ms")

# Now: what does the epc_pressure_penalty add?
# Reset nodes
fast_node.assigned_count = 0
slow_node.assigned_count = 0
print(f"\nEPC penalty (fast, 0 assigned): {epc_pressure_penalty(task, fast_node):.4f}")
print(f"EPC penalty (slow, 0 assigned): {epc_pressure_penalty(task, slow_node):.4f}")
fast_node.assigned_count = 2
slow_node.assigned_count = 2
print(f"EPC penalty (fast, 2 assigned): {epc_pressure_penalty(task, fast_node):.4f}")
print(f"EPC penalty (slow, 2 assigned): {epc_pressure_penalty(task, slow_node):.4f}")

# Key question: the epc_pressure_penalty is added to tee_service in execute_task.
# But HOW MUCH does it actually add in ms?
print(f"\n=== EPC PENALTY MAGNITUDE IN MS ===")
for count in [0, 1, 2, 5, 10, 50, 100]:
    fast_node.assigned_count = count
    p = epc_pressure_penalty(task, fast_node)
    print(f"  Fast node, {count:3d} assigned: penalty = {p:.4f}ms (out of ~20ms base service)")

# What are the ACTUAL latency drivers?
print(f"\n=== LATENCY BREAKDOWN (fast node, first task) ===")
fast_node2 = FogNode(node_id=0, tee_rate=3.5, ree_rate=3.5, network_ms=10.0,
                     epc_total_mb=90, trust=0.95, energy_factor=1.0)
rng = np.random.default_rng(42)
net = max(0.5, fast_node2.network_ms + rng.normal(0.0, 0.12 * fast_node2.network_ms))
print(f"  Network: {net:.2f}ms")
tee_base = task.tee_work / fast_node2.tee_rate
print(f"  TEE base service: {tee_base:.2f}ms")
print(f"  TEE startup: {SIMULATION_PARAMS['tee_startup_ms']}ms")
epc_p = epc_pressure_penalty(task, fast_node2)
print(f"  EPC penalty: {epc_p:.4f}ms")
ree_base = task.ree_work / fast_node2.ree_rate
print(f"  REE base service: {ree_base:.2f}ms")
print(f"  REE startup: {SIMULATION_PARAMS['ree_startup_ms']}ms")
print(f"  Finalization: {SIMULATION_PARAMS['finalization_ms']}ms")
print(f"  Total estimate: {net + tee_base + SIMULATION_PARAMS['tee_startup_ms'] + epc_p + ree_base + SIMULATION_PARAMS['ree_startup_ms'] + SIMULATION_PARAMS['finalization_ms']:.2f}ms")

# Now the slow node
print(f"\n=== LATENCY BREAKDOWN (slow node, first task) ===")
slow_node2 = FogNode(node_id=1, tee_rate=0.8, ree_rate=0.8, network_ms=10.0,
                     epc_total_mb=512, trust=0.95, energy_factor=1.0)
rng2 = np.random.default_rng(42)
net2 = max(0.5, slow_node2.network_ms + rng2.normal(0.0, 0.12 * slow_node2.network_ms))
print(f"  Network: {net2:.2f}ms")
tee_base2 = task.tee_work / slow_node2.tee_rate
print(f"  TEE base service: {tee_base2:.2f}ms")
print(f"  TEE startup: {SIMULATION_PARAMS['tee_startup_ms']}ms")
epc_p2 = epc_pressure_penalty(task, slow_node2)
print(f"  EPC penalty: {epc_p2:.4f}ms")
ree_base2 = task.ree_work / slow_node2.ree_rate
print(f"  REE base service: {ree_base2:.2f}ms")
print(f"  REE startup: {SIMULATION_PARAMS['ree_startup_ms']}ms")
print(f"  Finalization: {SIMULATION_PARAMS['finalization_ms']}ms")
print(f"  Total estimate: {net2 + tee_base2 + SIMULATION_PARAMS['tee_startup_ms'] + epc_p2 + ree_base2 + SIMULATION_PARAMS['ree_startup_ms'] + SIMULATION_PARAMS['finalization_ms']:.2f}ms")
