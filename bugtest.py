# test_decisions_v2.py — includes execute step like the real simulation
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
from phase4_load_balance.graph7 import (
    generate_enclaves, generate_tasks, choose_enclave, 
    clone_enclaves, execute_on_enclave, _drain_queues
)
import config

rng = np.random.default_rng(42)
base_enclaves = generate_enclaves(4, rng)
tasks = generate_tasks(100, np.random.default_rng(42), offered_load=0.7)
epc_req = config.PACKET_EPC_BYTES * 28

results = {}
for alg in ["Round-Robin", "Least-Queue", "Spider++ (Ours)"]:
    encs = clone_enclaves(base_enclaves)
    rng2 = np.random.default_rng(42 + 7)
    seq = []
    latencies = []
    for i, t in enumerate(tasks):
        _drain_queues(encs, t.arrival_ms, epc_per_task=epc_req)
        e = choose_enclave(encs, i, t, epc_req, alg, rng2)
        seq.append(e.enc_id if hasattr(e, 'enc_id') else 0)
        lat = execute_on_enclave(e, t, epc_req, rng2)
        latencies.append(lat)
    results[alg] = (seq, latencies)

print("First 20 decisions:")
for alg, (seq, _) in results.items():
    print(f"  {alg[:18]:18s}: {seq[:20]}")

from collections import Counter
print("\nDistribution across enclaves:")
for alg, (seq, _) in results.items():
    c = Counter(seq)
    print(f"  {alg[:18]:18s}: {dict(sorted(c.items()))}")

print("\nMean latency:")
for alg, (_, lats) in results.items():
    print(f"  {alg[:18]:18s}: {np.mean(lats):.1f} ms")

# Critical: are decision sequences and latencies different?
rr_seq = results["Round-Robin"][0]
sp_seq = results["Spider++ (Ours)"][0]
lq_seq = results["Least-Queue"][0]
print(f"\nDecisions different? Spider++ vs RR: {rr_seq != sp_seq}, vs LQ: {lq_seq != sp_seq}")

rr_lat = np.mean(results["Round-Robin"][1])
sp_lat = np.mean(results["Spider++ (Ours)"][1])
lq_lat = np.mean(results["Least-Queue"][1])
print(f"Latency gap: Spider++ vs RR: {(rr_lat-sp_lat)/rr_lat*100:.1f}%, vs LQ: {(lq_lat-sp_lat)/lq_lat*100:.1f}%")