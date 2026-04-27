# bugtest_v4.py — print Spider++ score breakdown for each enclave
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
from phase4_load_balance.graph8 import (
    generate_enclaves, generate_tasks, choose_enclave, 
    clone_enclaves, execute_on_enclave, _drain_queues,
    _enclave_score_eq46, _load_phase5_service_ms,
    SIMULATION_PARAMS
)
import config

rng = np.random.default_rng(42)
base_enclaves = generate_enclaves(4, rng)
tasks = generate_tasks(100, np.random.default_rng(42), offered_load=0.7)
epc_req = config.PACKET_EPC_BYTES * 28

encs_sp = clone_enclaves(base_enclaves)
rng_sp = np.random.default_rng(42 + 7)

# Run a few tasks then break down task 2's decision
for i, t in enumerate(tasks):
    _drain_queues(encs_sp, t.arrival_ms, epc_per_task=epc_req)
    
    if i == 2:  # Detailed breakdown for task 2
        print(f"\n=== Task {i} arrival_ms={t.arrival_ms:.2f} ===")
        for e in encs_sp:
            queue_wait = max(0.0, e.available_ms - t.arrival_ms)
            base_ms = _load_phase5_service_ms()
            baseline_rate = 0.393
            service_est = base_ms * (baseline_rate / max(0.01, e.service_rate))
            cont_per_unit = SIMULATION_PARAMS["contention_per_unit_ms"]
            norm_load = e.queue_length / max(0.1, e.service_rate)
            contention_cost = norm_load * cont_per_unit
            T_wait = queue_wait + service_est + contention_cost
            
            M_free = max(1.0, e.epc_available)
            ratio = epc_req / M_free - 0.5
            P_epc = max(0.0, ratio) ** 2
            if e.epc_available < epc_req:
                depletion = 1.0 - max(0.0, e.epc_available) / max(1.0, e.epc_total)
                epc_base = SIMULATION_PARAMS["epc_swap_base_ms"]
                P_epc += (0.5 + depletion) * epc_base
            
            P_cont = e.contention + e.queue_length / max(1.0, e.service_rate)
            
            affinity_window = getattr(config, 'ENCLAVE_AFFINITY_WINDOW', 20)
            A_affin = min(1.0, e.recent_count / max(1.0, affinity_window))
            
            z1 = config.Z1_ENC_WAIT
            z2 = config.Z2_ENC_EPC
            z3 = config.Z3_ENC_CONTENTION
            z4 = config.Z4_ENC_AFFIN
            
            total = z1*T_wait + z2*P_epc + z3*P_cont - z4*A_affin
            
            print(f"\n  E{e.enc_id} (q={e.queue_length}, avail_ms={e.available_ms:.1f}, rate={e.service_rate:.3f}, epc={e.epc_available:.0f}):")
            print(f"    queue_wait = max(0, {e.available_ms:.1f} - {t.arrival_ms:.1f}) = {queue_wait:.2f}")
            print(f"    service_est = {base_ms:.1f} * ({baseline_rate}/{e.service_rate:.3f}) = {service_est:.2f}")
            print(f"    contention_cost = {norm_load:.2f} * {cont_per_unit} = {contention_cost:.2f}")
            print(f"    T_wait        = {T_wait:.2f}")
            print(f"    P_epc         = {P_epc:.4f}")
            print(f"    P_cont        = {P_cont:.4f}")
            print(f"    A_affin       = {A_affin:.4f} (recent_count={e.recent_count})")
            print(f"    Components: z1*T_wait={z1*T_wait:.2f}  z2*P_epc={z2*P_epc:.4f}  z3*P_cont={z3*P_cont:.4f}  -z4*A={-z4*A_affin:.4f}")
            print(f"    SCORE         = {total:.2f}")
        break
    
    e = choose_enclave(encs_sp, i, t, epc_req, "Spider++ (Ours)", rng_sp)
    execute_on_enclave(e, t, epc_req, rng_sp)