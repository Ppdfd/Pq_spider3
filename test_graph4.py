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
    
    sk_u = aa.keygen({}, user_attrs)
    policy = {"type": "AND", "attributes": user_attrs}
    policy_pkg = aa.ree_build_policy(policy)
    k_aes = b"12345678901234567890123456789012"
    tee_out = aa.tee_partial_encrypt(k_aes, policy_pkg)
    ct = aa.ree_finalize_ct(policy_pkg, tee_out)
    
    t0 = time.perf_counter()
    pe = aa.policy_eval(ct, sk_u)
    if pe is not None:
        aa.cpabe_decrypt(ct, sk_u, pe)
    t_ours = (time.perf_counter() - t0) * 1000
    
    print(f"Attrs: {n_attr} | Decrypt: {t_ours:.2f} ms")

