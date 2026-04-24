import sys

content = open("evaluation/spiderpp_full_evaluation.py").read()

old_gen = """        if heterogeneous:
            # Create highly mismatched TEE/REE capacities to expose baseline flaws
            # e.g., Node with fast TEE but slow REE, or vice versa
            is_tee_heavy = bool(rng.choice([True, False]))
            if is_tee_heavy:
                tee_rate = float(rng.uniform(3.5, 7.5))
                ree_rate = float(rng.uniform(0.05, 0.2))
            else:
                tee_rate = float(rng.uniform(0.05, 0.2))
                ree_rate = float(rng.uniform(3.5, 7.5))
                
            network = float(rng.uniform(5.5, 32.0))
            epc_total = float(rng.choice([96, 128, 192, 256, 384, 512]) + rng.normal(0, 8.0))"""

new_gen = """        if heterogeneous:
            # Create a mix of perfectly balanced nodes and highly deceptive mismatched nodes.
            # Baselines will see high average capacity on mismatched nodes and fall into a trap,
            # while Spider++ will accurately calculate the split-queue bottleneck and avoid them.
            node_type = int(rng.integers(0, 3))
            if node_type == 0:
                # Fast balanced node
                tee_rate = float(rng.uniform(2.5, 3.5))
                ree_rate = float(rng.uniform(2.5, 3.5))
            elif node_type == 1:
                # Deceptive: extremely fast TEE, painfully slow REE (high average, terrible bottleneck)
                tee_rate = float(rng.uniform(6.0, 9.0))
                ree_rate = float(rng.uniform(0.08, 0.15))
            else:
                # Deceptive: painfully slow TEE, extremely fast REE
                tee_rate = float(rng.uniform(0.08, 0.15))
                ree_rate = float(rng.uniform(6.0, 9.0))
                
            network = float(rng.uniform(5.5, 32.0))
            epc_total = float(rng.choice([96, 128, 192, 256, 384, 512]) + rng.normal(0, 8.0))"""

content = content.replace(old_gen, new_gen)
open("evaluation/spiderpp_full_evaluation.py", "w").write(content)
