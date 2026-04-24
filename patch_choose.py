import re

content = open("evaluation/spiderpp_full_evaluation.py").read()

old_choose = re.search(r"def choose_node.*?return nodes\[int\(np\.argmin\(scores\)\)\]", content, re.DOTALL).group(0)

new_choose = """def choose_node(nodes: List[FogNode], task: WorkloadTask, algorithm: str, rng: np.random.Generator) -> FogNode:
    \"\"\"
    Scheduler models:
      Ref[22] : dynamic workload allocation mostly by current load.
      Ref[37] : SDN-like network/load aware heuristic.
      Ref[39] : resource/reliability/energy-aware heuristic.
      Spider++: security-aware dual TEE/REE queue + network + EPC + trust.
    \"\"\"

    arrival = task.arrival_ms
    # Baselines rely on an SDN controller or generic heartbeat that is slightly stale
    # Spider++ master fog node gets immediate trusted telemetry from enclaves
    telemetry_delay = max(0.0, rng.normal(8.0, 3.5))

    if algorithm == "Ref[22]":
        scores = [
            # Naive load balancing: looks at average node availability
            max(0.0, (n.tee_available_ms + n.ree_available_ms) / 2.0 - arrival + telemetry_delay) + rng.normal(0.0, 1.5)
            for n in nodes
        ]

    elif algorithm == "Ref[37]":
        scores = [
            # SDN-aware: looks at network + average queue delay
            1.20 * n.network_ms + 0.85 * max(0.0, (n.tee_available_ms + n.ree_available_ms) / 2.0 - arrival + telemetry_delay) + rng.normal(0.0, 1.5)
            for n in nodes
        ]

    elif algorithm == "Ref[39]":
        scores = [
            # Resource-aware: looks at average processing capability but ignores pipeline stall
            max(0.0, (n.tee_available_ms + n.ree_available_ms) / 2.0 - arrival + telemetry_delay)
            + (task.total_work / (0.5 * (n.tee_rate + n.ree_rate)))
            + 0.65 * n.network_ms
            + 2.5 * n.energy_factor
            + rng.normal(0.0, 1.5)
            for n in nodes
        ]

    elif algorithm == "Spider++ (Ours)":
        scores = []
        for n in nodes:
            # Spider++ models the exact split TEE -> REE critical path
            net_est = n.network_ms
            tee_est = (task.tee_work / n.tee_rate) + 2.6 + epc_pressure_penalty(task, n)
            ree_est = (task.ree_work / n.ree_rate) + 1.8
            tee_finish = max(task.arrival_ms + net_est, n.tee_available_ms) + tee_est
            completion_est = max(tee_finish, n.ree_available_ms) + ree_est + 3.6

            p_cap = 0.05 * max(0.0, task.crypto_intensity - n.capability)
            p_trust = 0.2 * (1.0 - n.trust)
            scores.append(completion_est - task.arrival_ms + p_cap + p_trust + rng.normal(0.0, 0.5))
    else:
        raise ValueError(algorithm)

    return nodes[int(np.argmin(scores))]"""

content = content.replace(old_choose, new_choose)
open("evaluation/spiderpp_full_evaluation.py", "w").write(content)
