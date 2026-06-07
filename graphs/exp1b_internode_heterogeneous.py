"""
Graph 6: Heterogeneous Fog-Node Load Balancing
================================================

Uses the SAME simulation pipeline as Graph 5 (graph_load_balancing)
with heterogeneous=True.

FAIRNESS AUDIT NOTE:
  Previously this file contained hardcoded numpy arrays that were
  not derived from any simulation or measurement. It has been replaced
  with a proper call to the shared simulation function so that all
  algorithms are evaluated on identical task streams, node populations,
  and execution engines.
"""

from typing import Dict
import numpy as np

from graphs.exp1a_internode_homogeneous import graph1_load_balancing


def graph2_heterogeneous_fog(
    rng: np.random.Generator, reps: int = 20
) -> Dict[str, np.ndarray]:
    """Graph 2: Heterogeneous fog-node load-balancing latency"""
    return graph1_load_balancing(rng, graph_no=6, heterogeneous=True, reps=reps)
