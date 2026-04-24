"""
Phase III (Ours): PQ-SPIDER Gateway Validation and Micro-Batch Formation
===================================================================
Matches PQ-SPIDER paper Sec III-C, Phase III (Eq 21-24, Algorithm 1):

  Eq 21: k_gkem,i ← Decap_Kyber(c_gkem,i)     — Gateway Kyber decap
  Eq 22: Auth'_i ← MAC_{k_gkem}(...)           — Recompute MAC
  Eq 23: GTag ← H(Sort({Auth_i}) ∥ t_G)        — Group auth tag
  Eq 24: B_k = ⟨BID, P_valid, GTag, t_G⟩       — Micro-batch
"""

import sys
import config
import time
import hmac
import hashlib
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from crypto_primitives.kyber import SecureKyber
from utils.dataset_loader import DataLoader

REPLAY_WINDOW_S = 60


def _verify_auth(packet: dict, sk_gw: bytes) -> tuple[bool, float]:
    """Eq 21: k_gkem ← Decap_Kyber(c_gkem)
       Eq 22: Auth'_i ← MAC_{k_gkem}(ID ∥ Meta ∥ c_kem ∥ CT ∥ Tag ∥ t)"""
    t_start = time.perf_counter()

    kyber_gw = SecureKyber()
    cg_kem = bytes.fromhex(packet["cg_kem"])
    kg_kem = kyber_gw.decap(cg_kem, sk_gw)

    metadata = bytes.fromhex(packet["metadata"])
    msg = (packet["device_id"].encode()
           + metadata
           + bytes.fromhex(packet["c_kem"])
           + bytes.fromhex(packet["ct_i"])
           + str(packet["timestamp"]).encode())
    expected = hmac.new(kg_kem, msg, hashlib.sha256).digest()

    auth_ok = hmac.compare_digest(expected, bytes.fromhex(packet["auth_i"]))
    t_elapsed = (time.perf_counter() - t_start) * 1000
    return auth_ok, t_elapsed


def _within_replay_window(packet: dict, now: float) -> bool:
    return abs(now - float(packet["timestamp"])) <= REPLAY_WINDOW_S


def run_phase3_simulation():
    print("=" * 60)
    print("PQ-SPIDER Phase 3 Simulation: Edge Gateway Validation (Ours)")
    print("=" * 60)

    loader = DataLoader()
    phase1_dir = Path(__file__).parent.parent / "phase1_initialization"
    phase2_dir = Path(__file__).parent.parent / "phase2_iiot_encrypt"
    try:
        gw_key = loader.load_data(phase1_dir, "ours_gw_key.json")
        packets = loader.load_data(phase2_dir, "ours_packets.json")
    except FileNotFoundError:
        print("  ! Run phase1 and phase2 first.")
        return

    sk_gw = bytes.fromhex(gw_key["sk"])

    metrics = {
        "auth_verify_per_pkt":   [],
        "replay_check_per_pkt":  [],
        "batch_tag_construct":   0,
        "total_gateway_latency": 0,
        "dropped_count":         0,
        "forwarded_count":       0,
    }

    print(f"  -> Received {len(packets)} packets from IIoT layer.")
    start = time.perf_counter()
    now = time.time()

    forwarded = []
    for p in packets:
        auth_ok, t_decap_and_mac = _verify_auth(p, sk_gw)
        metrics["auth_verify_per_pkt"].append(t_decap_and_mac)

        t0 = time.perf_counter()
        time_ok = _within_replay_window(p, now)
        metrics["replay_check_per_pkt"].append((time.perf_counter() - t0) * 1000)

        if auth_ok and time_ok:
            forwarded.append(p)
        else:
            metrics["dropped_count"] += 1
            print(f"  -> DROP {p['device_id']} (auth={auth_ok}, time={time_ok})")

    metrics["forwarded_count"] = len(forwarded)

    # Eq 23: GTag ← H(Sort({Auth_i | P_i ∈ P_valid}) ∥ t_G)
    t0 = time.perf_counter()
    auths = sorted(bytes.fromhex(p["auth_i"]) for p in forwarded)
    t_G = str(int(now)).encode()
    g_tag = hashlib.sha256(b"".join(auths) + t_G).digest()
    metrics["batch_tag_construct"] = (time.perf_counter() - t0) * 1000

    metrics["total_gateway_latency"] = (time.perf_counter() - start) * 1000

    # AUDIT FIX: Negative-case sanity test now runs OUTSIDE the
    # timed window.  It's a correctness check, not gateway work.
    if packets:
        p0 = dict(packets[0])
        bad = bytearray(bytes.fromhex(p0["auth_i"]))
        bad[0] ^= 0xFF
        p0["auth_i"] = bytes(bad).hex()
        auth_ok, _ = _verify_auth(p0, sk_gw)
        assert not auth_ok, "Negative-case auth should fail"

    loader.save_metrics(Path(__file__).parent, metrics)
    loader.save_data(Path(__file__).parent, "ours_batch.json", {
        "g_tag":   g_tag.hex(),
        "t_G":     t_G.hex(),
        "packets": forwarded,
    })

    if len(packets) > 0:
        avg_auth = sum(metrics["auth_verify_per_pkt"]) / len(packets)
        avg_repl = sum(metrics["replay_check_per_pkt"]) / len(packets)
        print(f"\n[1] Auth verify (Kyber decap + MAC) (avg/pkt) : "
              f"{avg_auth:.4f} ms")
        print(f"[2] Replay check (avg/pkt): {avg_repl:.4f} ms")

    print(f"[3] G_Tag construct : {metrics['batch_tag_construct']:.4f} ms")
    print(f"  Forwarded: {metrics['forwarded_count']} / "
          f"Dropped: {metrics['dropped_count']}")
    print("\n" + "=" * 60)
    print(f"Phase 3 (Ours) Finished. Total: "
          f"{metrics['total_gateway_latency']:.2f} ms")
    print("=" * 60)
    return metrics


if __name__ == "__main__":
    run_phase3_simulation()
