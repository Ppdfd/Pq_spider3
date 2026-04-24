"""
OP-TEE Benchmark Measurement Loader
====================================
Reads measured_values.json (produced by pqspider_bench TA on QEMU)
and patches config.py values at runtime.

Usage:
    from phase4_load_balance.optee_bench.loader import load_measurements
    load_measurements()   # call once before Phase 4 runs

The JSON file is auto-written by the TA via VirtFS when you run:
    cd ~/optee-qemu/build && make QEMU_VIRTFS_AUTOMOUNT=y run
    # inside QEMU: pqspider_bench
"""

import json
import os
import sys
from pathlib import Path

# Resolve paths
_HERE = Path(__file__).parent
_JSON = _HERE / "measured_values.json"


def load_measurements(config_module=None):
    """
    Load OP-TEE benchmark results and patch config at runtime.

    Args:
        config_module: the config module to patch. If None, imports config.
    Returns:
        dict with the measured values.
    """
    if config_module is None:
        # Add project root to path if needed
        root = _HERE.parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        import config as config_module

    if not _JSON.exists():
        print(f"  [optee_bench] No measurements found at {_JSON}")
        print(f"  [optee_bench] Using config.py defaults.")
        return {
            "service_rate":   config_module.MEASURED_SERVICE_RATE,
            "world_switch_ms": config_module.MEASURED_WORLD_SWITCH_MS,
            "trust_score":    config_module.MEASURED_BASE_TRUST,
            "source":         "config.py defaults",
        }

    with open(_JSON) as f:
        data = json.load(f)

    # Patch config module
    if "service_rate" in data:
        config_module.MEASURED_SERVICE_RATE = data["service_rate"]
    if "world_switch_ms" in data:
        config_module.MEASURED_WORLD_SWITCH_MS = data["world_switch_ms"]
    if "trust_score" in data:
        config_module.MEASURED_BASE_TRUST = data["trust_score"]

    source = data.get("source", "measured_values.json")
    print(f"  [optee_bench] Loaded: rate={data.get('service_rate')}, "
          f"latency={data.get('world_switch_ms')}ms, "
          f"trust={data.get('trust_score')}")
    print(f"  [optee_bench] Source: {source}")

    return data


if __name__ == "__main__":
    # Quick test: load and print
    data = load_measurements()
    print(json.dumps(data, indent=2))
