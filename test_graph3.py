import time
import numpy as np
from crypto_primitives.cp_abe import LatticeCPABE

attrs = np.arange(5, 55, 5)

for n_attr in attrs:
    universe = [f"Attr{i}" for i in range(int(n_attr))]
    user_attrs = universe
    aa = LatticeCPABE(n=256, q=3329)
    aa.setup()
    for a in universe:
        aa.hash_attribute(a)
    
    # Ref[4] time (no cache: build policy + encrypt)
    t0 = time.perf_counter()
    policy = {"type": "AND", "attributes": user_attrs}
    k_aes = b"12345678901234567890123456789012"
    ct_labe = aa.encrypt(k_aes, policy)
    t_ref4 = (time.perf_counter() - t0) * 1000

    # Ours time (with cache: TEE partial + REE finalize)
    policy_pkg = aa.ree_build_policy(policy)
    t0 = time.perf_counter()
    tee_out = aa.tee_partial_encrypt(k_aes, policy_pkg)
    ct_ours = aa.ree_finalize_ct(policy_pkg, tee_out)
    t_ours = (time.perf_counter() - t0) * 1000
    
    print(f"Attrs: {n_attr} | Ref[4]: {t_ref4:.2f} ms | Ours: {t_ours:.2f} ms")

