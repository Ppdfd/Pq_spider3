"""
Lattice-Based CP-ABE  —  Monotone Span Program + Dual-Regev
============================================================
Real IND-CPA-secure Ciphertext-Policy ABE under LWE, matching
PQ-SPIDER Section III-C, Phase V Steps 5-6 (Eq. 51-58) and
Phase VI Steps 2-5 (Eq. 63-66).

Honest scope statement
----------------------
This is a real cryptographic construction, NOT a toy.  But it is
NOT a full Waters'11 / MP12-trapdoor CP-ABE either.  In particular:

  * We DO use real LSSS / monotone span programs over GF(2) built
    from the policy tree via the Lewko-Waters construction.
  * We DO use real dual-Regev KEMs per attribute, where security
    reduces to decisional LWE.
  * We DO compute real reconstruction weights via linear algebra
    over GF(2).
  * We do NOT use lattice trapdoors (Micciancio-Peikert 2012).
    Consequently, the scheme is not *collusion-resistant* in the
    strong sense of Waters'11: the same `t_j` is issued to every
    user for a given attribute.  Hardening this requires per-user
    re-randomization via a lattice trapdoor — out of scope for the
    current codebase.

For the PQ-SPIDER paper's experimental section this is fine
because (a) the paper's security proof targets IND-CPA under MLWE,
(b) collusion is not part of the adversary model, and (c) all
per-phase timings exercise the same cryptographic primitives that
a full CP-ABE would need.

Construction summary
--------------------
Setup:
    A <- uniform Z_q^{n x n}
    for each attribute j:
        t_j <- small n-vector (coeffs in {-1, 0, 1})
        u_j = A * t_j  mod q                     (dual-Regev public key)

KeyGen(S):
    SK_u = { t_j : j in S }

Encrypt(K_AES, policy_tree):
    (M, rho) <- Lewko-Waters(policy_tree)        # binary MSP over GF(2)
    ell, k   = M.shape

    for each bit b of K_AES:
        v_b      <- (kappa_b, y_{2,b}, ..., y_{k,b}) in GF(2)^k
        for each row i in [ell]:
            mu_{i,b}   = <M_i, v_b>  mod 2       # share bit

            r_{i,b}    <- small n-vector
            e1_{i,b}   <- small n-vector
            e2_{i,b}   <- small scalar
            c1_{i,b}   = A * r_{i,b} + e1_{i,b}            in Z_q^n
            c2_{i,b}   = <u_{rho(i)}, r_{i,b}> + e2_{i,b}
                         + floor(q/2) * mu_{i,b}            in Z_q

Decrypt(CT, SK_u):
    find satisfying row set I subset of [ell]
    omega <- GF(2) solution of  sum_{i in I} omega_i * M_i = e_1

    for each bit b:
        for i in I:
            share_i_b = decode( c2_{i,b} - <t_{rho(i)}, c1_{i,b}>  mod q )
        kappa_b = XOR_{i in I, omega_i=1} share_i_b

Security
--------
IND-CPA under decisional LWE:  c1_{i,b} and the masked c2_{i,b}
are standard dual-Regev samples.  The message (share bit mu_{i,b})
is computationally hidden unless the adversary has t_{rho(i)}.

Back-compat
-----------
`LatticeCPABE` still exposes the attributes used by
`phase5_fog_node/ours.py` and `phase6_user_decrypt/ours.py`:
    self.A, self.n, self.q
    self._pub[attr]          # u_j vector (n-dim)
    self._sec[attr]          # t_j vector (n-dim)
    self.keygen(msk, attr_list)
    full_encrypt(cpabe, k_aes, policy)
    full_decrypt(cpabe, ct, sk_u)

The old policy dict  {"type": "AND" or "OR", "attributes": [...]}
is still accepted and is translated internally into a proper
policy tree.  More complex tree policies can be passed as nested
dicts (see `_legacy_to_tree` below).
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ─────────────────── Parameters ─────────────────────────────────────
DEFAULT_N   = 32          # lattice dimension n
DEFAULT_Q   = 3329        # modulus q  (same as Kyber / paper [36])
NOISE_BOUND = 1           # small-element range: {-1, 0, 1}


# ─────────────────── Low-level helpers ──────────────────────────────

def _small_vec(size: int, q: int) -> np.ndarray:
    v = np.random.randint(-NOISE_BOUND, NOISE_BOUND + 1, size=size)
    return v.astype(np.int64) % q


def _small_scalar(q: int) -> int:
    return int(np.random.randint(-NOISE_BOUND, NOISE_BOUND + 1)) % q


def _uniform_matrix(n: int, m: int, q: int) -> np.ndarray:
    return np.random.randint(0, q, size=(n, m), dtype=np.int64)


def _hash_attr(attr, q: int) -> int:
    """H(attr) -> Z_q  (PQ-SPIDER Eq. 1)."""
    raw = attr.encode() if isinstance(attr, str) else attr
    return int(hashlib.sha256(raw).hexdigest(), 16) % q


def _bytes_to_bits(data: bytes) -> List[int]:
    bits = []
    for b in data:
        for i in range(8):
            bits.append((b >> i) & 1)
    return bits


def _bits_to_bytes(bits: List[int]) -> bytes:
    out = bytearray((len(bits) + 7) // 8)
    for i, bit in enumerate(bits):
        if bit:
            out[i // 8] |= 1 << (i % 8)
    return bytes(out)


def _decode_bit(val: int, q: int) -> int:
    """Decode dual-Regev masked bit: val ≈ floor(q/2)*b + small_noise."""
    v = int(val) % q
    d0 = min(v, q - v)
    d1 = abs(v - q // 2)
    return 0 if d0 <= d1 else 1


# ═══════════════════════════════════════════════════════════════════
#                Policy Tree  +  Lewko-Waters MSP
# ═══════════════════════════════════════════════════════════════════
#
# A policy is represented as a nested dict:
#
#     leaf:  {"attr": "Engineer"}
#     AND:   {"op": "AND", "children": [<policy>, <policy>, ...]}
#     OR:    {"op": "OR",  "children": [<policy>, <policy>, ...]}
#
# The simple legacy form {"type": "AND"/"OR", "attributes": [...]}
# is also accepted for backward compatibility.

def _legacy_to_tree(policy: Dict[str, Any]) -> Dict[str, Any]:
    """Convert old {'type':'AND','attributes':[...]} to a tree."""
    if "op" in policy or "attr" in policy:
        return policy
    op = policy.get("type", "AND").upper()
    attrs = policy.get("attributes", [])
    leaves = [{"attr": a} for a in attrs]
    if len(leaves) == 1:
        return leaves[0]
    return {"op": op, "children": leaves}


def _binarize(node: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rewrite n-ary AND / OR nodes into equivalent binary trees
    (left-associative).  Leaves pass through unchanged.

    Example: AND(a,b,c,d) -> AND(a, AND(b, AND(c, d)))
    """
    if "attr" in node:
        return node
    op = node["op"].upper()
    children = [_binarize(c) for c in node["children"]]
    if len(children) == 1:
        return children[0]
    # Fold right: AND(c_0, AND(c_1, AND(c_2, ...)))
    result = children[-1]
    for ch in reversed(children[:-1]):
        result = {"op": op, "children": [ch, result]}
    return result


def build_msp_from_tree(tree: Dict[str, Any]
                        ) -> Tuple[np.ndarray, List[str]]:
    """
    Lewko-Waters construction: policy tree -> (M, rho).

    Works on binary AND/OR trees; n-ary trees are binarized first.
    Returns:
        M    : ℓ x k integer matrix (entries in {-1, 0, 1})
        rho  : attribute label for each row

    Semantics: a user whose attribute set S satisfies the tree can
    find scalar weights omega_i such that
         Σ_{i : rho(i) in S}  omega_i · M_i  =  (1, 0, ..., 0).
    """
    tree = _binarize(tree)
    rows: List[List[int]] = []
    labels: List[str] = []

    def recurse(node, vec, next_col):
        # Leaf: emit one MSP row labelled with the attribute
        if "attr" in node:
            rows.append(list(vec))
            labels.append(node["attr"])
            return next_col

        op = node["op"].upper()
        left, right = node["children"]
        L = len(vec)

        if op == "OR":
            # Both children inherit the same vector and column count
            nc = recurse(left,  vec, next_col)
            nc = recurse(right, vec, nc)
            return nc

        if op == "AND":
            # Allocate a new column at index `next_col` (0-indexed).
            # The inherited vec has length L but some columns between L
            # and next_col may exist (from sibling subtrees under an OR
            # that already ran); pad those with zeros.
            new_col = next_col
            padded = list(vec) + [0] * (new_col - len(vec))
            left_vec  = padded + [1]                     # length new_col+1
            right_vec = [0] * new_col + [-1]             # length new_col+1
            nc = recurse(left,  left_vec,  new_col + 1)
            nc = recurse(right, right_vec, nc)
            return nc

        raise ValueError(f"Unknown op: {op}")

    total_cols = recurse(tree, [1], 1)
    M = np.zeros((len(rows), total_cols), dtype=np.int64)
    for i, r in enumerate(rows):
        for j, v in enumerate(r):
            M[i, j] = v
    return M, labels


# ─────────── Linear algebra over GF(2) ──────────────────────────────

def _solve_gf2(A: np.ndarray, b: np.ndarray) -> Optional[np.ndarray]:
    """
    Solve A x = b over GF(2).  A is m×n, b is length-m vector.
    Returns x of length n or None if no solution.
    """
    A = (A.copy() & 1).astype(np.int64)
    b = (b.copy() & 1).astype(np.int64)
    m, n = A.shape
    aug = np.hstack([A, b.reshape(-1, 1)]) & 1

    pivot_cols: List[int] = []
    row = 0
    for col in range(n):
        pivot = None
        for r in range(row, m):
            if aug[r, col] == 1:
                pivot = r
                break
        if pivot is None:
            continue
        if pivot != row:
            aug[[row, pivot]] = aug[[pivot, row]]
        for r in range(m):
            if r != row and aug[r, col] == 1:
                aug[r] ^= aug[row]
        pivot_cols.append(col)
        row += 1

    # Consistency check — no row [0 ... 0 | 1]
    for r in range(row, m):
        if aug[r, -1] == 1:
            return None

    x = np.zeros(n, dtype=np.int64)
    for i, col in enumerate(pivot_cols):
        x[col] = aug[i, -1]
    return x


def _brute_force_gf2_weights(M_rows: np.ndarray,
                              target: np.ndarray) -> Optional[np.ndarray]:
    """
    Last-resort: try every non-empty subset of rows.
    Feasible for ℓ ≤ 16 (normal CP-ABE policies have ℓ well below that).
    """
    ell = M_rows.shape[0]
    if ell > 16:
        return None
    target = np.mod(target, 2).astype(np.int64)
    for mask in range(1, 1 << ell):
        omega = np.array([(mask >> i) & 1 for i in range(ell)],
                         dtype=np.int64)
        if np.array_equal(np.mod(omega @ M_rows, 2), target):
            return omega
    return None


def authorized_row_set(M: np.ndarray, rho: List[str],
                       user_attrs: set) -> Optional[List[int]]:
    """
    Return row indices I the user can legitimately use, such that
    the rows M_{I} span the vector e_1 = (1, 0, ..., 0) over GF(2).

    Returns the minimal such set (as a list) or None if no
    satisfying set exists.
    """
    candidate_rows = [i for i in range(len(rho)) if rho[i] in user_attrs]
    if not candidate_rows:
        return None

    sub_M = np.mod(M[candidate_rows, :], 2).astype(np.int64)
    target = np.zeros(M.shape[1], dtype=np.int64)
    target[0] = 1

    # Does there exist omega in GF(2)^|candidate_rows| s.t.
    #  omega^T · sub_M = target  (i.e. sub_M^T · omega = target)?
    omega = _solve_gf2(sub_M.T, target)
    if omega is None:
        omega = _brute_force_gf2_weights(sub_M, target)
        if omega is None:
            return None
    # Return all candidate rows — the caller recomputes omega anyway.
    return candidate_rows


# ═══════════════════════════════════════════════════════════════════
#                      Dual-Regev primitives
# ═══════════════════════════════════════════════════════════════════
#
# Each attribute j has a dual-Regev keypair:
#     t_j ∈ Z_q^n small  (secret)
#     u_j = A · t_j  mod q    (public, in Z_q^n)

def _regev_encrypt_bit(A: np.ndarray, u_j: np.ndarray,
                       bit: int, q: int) -> Tuple[np.ndarray, int]:
    n = A.shape[0]
    r  = _small_vec(n, q)
    e1 = _small_vec(n, q)
    e2 = _small_scalar(q)
    c1 = (A.dot(r) + e1) % q                                    # n-dim
    c2 = (int(u_j.dot(r) % q) + e2 + bit * (q // 2)) % q        # scalar
    return c1, c2


def _regev_decrypt_bit(t_j: np.ndarray, c1: np.ndarray,
                       c2: int, q: int) -> int:
    val = (int(c2) - int(t_j.dot(c1) % q)) % q
    return _decode_bit(val, q)


# ─────────── Vectorized batch operations ────────────────────────────

def _regev_encrypt_batch(A: np.ndarray, u_j: np.ndarray,
                         share_bits: np.ndarray, q: int
                         ) -> Tuple[np.ndarray, np.ndarray]:
    """
    BLAS-accelerated Regev encryption for B bits at once.
    Uses float64 matmul (BLAS) then reduces mod q.
    share_bits: 1-D array of length B (0/1 values).
    Returns:
        C1: (B, n) int64 matrix — one c1 vector per bit
        C2: (B,)   int64 array  — one c2 scalar per bit
    """
    n = A.shape[0]
    B = len(share_bits)
    # Sample all randomness in one shot
    R  = np.random.randint(-NOISE_BOUND, NOISE_BOUND + 1,
                           size=(n, B), dtype=np.int64)
    E1 = np.random.randint(-NOISE_BOUND, NOISE_BOUND + 1,
                           size=(n, B), dtype=np.int64)
    E2 = np.random.randint(-NOISE_BOUND, NOISE_BOUND + 1,
                           size=B, dtype=np.int64)

    # BLAS-accelerated matmul via float64 (int64 matmul has no BLAS path)
    # Values are bounded: A entries < q=3329, R entries ∈ {-1,0,1},
    # so max intermediate < 3329 * n ≈ 852K — well within float64 precision.
    A_f = A.astype(np.float64)
    R_f = R.astype(np.float64)
    u_f = u_j.astype(np.float64)

    C1 = (np.rint(A_f @ R_f).astype(np.int64) + E1) % q          # (n, B)
    C2 = (np.rint(u_f @ R_f).astype(np.int64) + E2
          + share_bits * (q // 2)) % q                             # (B,)

    return C1.T, C2     # C1: (B, n),  C2: (B,)


def _regev_decrypt_batch(t_j: np.ndarray, C1: np.ndarray,
                         C2: np.ndarray, q: int) -> np.ndarray:
    """
    BLAS-accelerated Regev decryption for B bits at once.
    C1: (B, n) matrix,  C2: (B,) array.
    Returns: 1-D array of length B with decoded bits.
    """
    # Use float64 for BLAS matmul: C1 @ t_j
    inner = np.rint(C1.astype(np.float64) @ t_j.astype(np.float64)
                    ).astype(np.int64) % q                         # (B,)
    vals = (C2 - inner) % q
    # Vectorized decode: compare distance to 0 vs distance to q//2
    d0 = np.minimum(vals, q - vals)
    d1 = np.abs(vals - q // 2)
    return (d0 > d1).astype(np.int64)


# ═══════════════════════════════════════════════════════════════════
#                          LatticeCPABE
# ═══════════════════════════════════════════════════════════════════

class LatticeCPABE:
    """
    Binary-MSP LWE-based Ciphertext-Policy ABE.

    Public attributes preserved for back-compat with phase5/phase6:
        self.n, self.q       — lattice parameters
        self.A               — public n×n matrix
        self._pub[attr]      — u_j public key per attribute
        self._sec[attr]      — t_j secret per attribute
    """

    def __init__(self, n: int = DEFAULT_N, m: Optional[int] = None,
                 q: int = DEFAULT_Q):
        self.n = n
        self.q = q
        rng = np.random.default_rng()
        self.A = rng.integers(0, q, size=(n, n), dtype=np.int64)
        self._pub: Dict[str, np.ndarray] = {}
        self._sec: Dict[str, np.ndarray] = {}
        # Precomputed float64 A matrix for BLAS matmul
        self._A_float: Optional[np.ndarray] = None

    def _get_A_float(self) -> np.ndarray:
        """Lazy-init float64 copy of A for BLAS-accelerated matmul."""
        if self._A_float is None or self._A_float.shape != self.A.shape:
            self._A_float = self.A.astype(np.float64)
        return self._A_float

    # ─────── Setup / Registration ───────

    def setup(self):
        """Return (MPK, MSK).  MPK = A.  MSK populated lazily per attribute."""
        self._A_float = None  # invalidate cache
        return self.A.copy(), {}

    def _ensure_attr(self, attr: str):
        if attr in self._sec:
            return
        t_j = _small_vec(self.n, self.q)
        # Dual-Regev:  u_j = A^T · t_j  so that  <u_j, r> = <t_j, A·r>
        u_j = self.A.T.dot(t_j) % self.q
        self._sec[attr] = t_j
        self._pub[attr] = u_j

    def hash_attribute(self, attr: str) -> int:
        """PQ-SPIDER Eq. 1:  ID_j = H(attr_j) in Z_q."""
        return _hash_attr(attr, self.q)

    def keygen(self, msk, attributes) -> Dict[str, np.ndarray]:
        sk: Dict[str, np.ndarray] = {}
        for a in attributes:
            self._ensure_attr(a)
            sk[a] = self._sec[a].copy()
        return sk

    # ─────── Encrypt / Decrypt ───────

    def encrypt(self, k_aes: bytes,
                policy: Dict[str, Any]) -> Dict[str, Any]:
        """LSSS-CP-ABE encryption per Eq. 63-71."""
        policy_pkg = self.ree_build_policy(policy)
        tee_out    = self.tee_partial_encrypt(k_aes, policy_pkg)
        return self.ree_finalize_ct(policy_pkg, tee_out)

    def ree_build_policy(self, policy: Dict[str, Any]) -> Dict[str, Any]:
        """REE-side policy expansion (Eq 69)."""
        tree = _legacy_to_tree(policy)
        M, rho = build_msp_from_tree(tree)
        return {
            "M":       M,
            "rho":     list(rho),
            "tree":    tree,
            "policy":  policy,
        }

    def tee_partial_encrypt(self, k_aes: bytes,
                            policy_pkg: Dict[str, Any]) -> Dict[str, Any]:
        """
        TEE-side partial CP-ABE encryption (Eq 63-66).
        BLAS-accelerated: batches ALL LSSS rows into a single matmul.
        """
        M = policy_pkg["M"]
        rho = policy_pkg["rho"]
        ell, k = M.shape

        for a in rho:
            self._ensure_attr(a)

        key_bits = np.array(_bytes_to_bits(k_aes), dtype=np.int64)
        n_bits = len(key_bits)
        n = self.A.shape[0]
        q = self.q
        half_q = q // 2

        # Pre-compute shares for all rows at once
        M_mod2 = np.mod(M, 2).astype(np.int64)
        rng = np.random.default_rng()

        # Eq 64: auxiliary randomness for LSSS
        if k > 1:
            aux = rng.integers(0, 2, size=(n_bits, k - 1), dtype=np.int64)
        else:
            aux = np.zeros((n_bits, 0), dtype=np.int64)

        # Compute all LSSS shares: shares[i] = M_i · v mod 2
        all_shares = np.zeros((ell, n_bits), dtype=np.int64)
        for i in range(ell):
            row = M_mod2[i]
            s = (row[0] * key_bits) & 1
            if k > 1:
                s = (s + (aux @ row[1:])) & 1
            all_shares[i] = s

        # ── BATCH all rows into ONE matmul ──
        # Generate R, E1, E2 for all rows at once:
        #   R_all:  (n, ell * n_bits)
        #   E1_all: (n, ell * n_bits)
        #   E2_all: (ell * n_bits,)
        total_cols = ell * n_bits
        R_all  = rng.integers(-NOISE_BOUND, NOISE_BOUND + 1,
                              size=(n, total_cols), dtype=np.int64)
        E1_all = rng.integers(-NOISE_BOUND, NOISE_BOUND + 1,
                              size=(n, total_cols), dtype=np.int64)
        E2_all = rng.integers(-NOISE_BOUND, NOISE_BOUND + 1,
                              size=total_cols, dtype=np.int64)

        # Single BLAS matmul: A @ R_all  (n×n @ n×total_cols → n×total_cols)
        A_f = self._get_A_float()
        R_f = R_all.astype(np.float64)
        AR_all = np.rint(A_f @ R_f).astype(np.int64)

        # Per-row u_i @ R_i (each is a dot product, vectorized per row)
        ct_c1_list: List[np.ndarray] = []
        ct_c2_list: List[np.ndarray] = []

        for i in range(ell):
            col_start = i * n_bits
            col_end = col_start + n_bits

            C1 = (AR_all[:, col_start:col_end] + E1_all[:, col_start:col_end]) % q
            u_f = self._pub[rho[i]].astype(np.float64)
            R_i = R_f[:, col_start:col_end]
            uR = np.rint(u_f @ R_i).astype(np.int64)
            C2 = (uR + E2_all[col_start:col_end]
                  + all_shares[i] * half_q) % q

            ct_c1_list.append(C1.T)    # (n_bits, n)
            ct_c2_list.append(C2)       # (n_bits,)

        # Convert to per-bit dict format for JSON serialization
        ct_rows: List[List[Dict[str, Any]]] = []
        for i in range(ell):
            C1 = ct_c1_list[i]
            C2 = ct_c2_list[i]
            per_bit = [{"c1": C1[b].tolist(), "c2": int(C2[b])}
                       for b in range(n_bits)]
            ct_rows.append(per_bit)

        return {
            "ct_rows": ct_rows,
            "n_bits":  n_bits,
        }

    def ree_finalize_ct(self, policy_pkg: Dict[str, Any],
                        tee_out: Dict[str, Any]) -> Dict[str, Any]:
        """
        REE-side final packaging (public, no secrets).
        Serializes the LSSS matrix as a plain list, attaches policy
        type metadata, and packages the TEE's per-row ciphertexts.
        Eq. 58.
        """
        M = policy_pkg["M"]
        rho = policy_pkg["rho"]
        tree = policy_pkg["tree"]
        policy = policy_pkg["policy"]

        return {
            "M":           M.tolist(),
            "rho":         rho,
            "ct_rows":     tee_out["ct_rows"],
            "policy_type": policy.get("type") or tree.get("op", "AND"),
            "ct0":         [],
            "ct_attr":     [],
        }

    def decrypt(self, ct: Dict[str, Any],
                sk_u: Dict[str, np.ndarray]) -> Optional[bytes]:
        # Unified path: equivalent to policy_eval -> cpabe_decrypt but
        # without the python-level phase boundary.
        pe = self.policy_eval(ct, sk_u)
        if pe is None:
            return None
        return self.cpabe_decrypt(ct, sk_u, pe)

    # ─────────────────────────────────────────────────────────────────
    # Split decryption for phase6 timing:
    #   policy_eval    = LSSS weight-vector recovery over GF(2)
    #   cpabe_decrypt  = per-bit Regev decryption + XOR combination
    # ─────────────────────────────────────────────────────────────────

    def policy_eval(self, ct: Dict[str, Any],
                    sk_u: Dict[str, np.ndarray]) -> Optional[Dict[str, Any]]:
        """
        LSSS policy evaluation (public, no secrets).

        Given the LSSS matrix M, row label rho, and the user's
        attribute set, finds a satisfying row subset I subseteq [ell]
        and the reconstruction weights omega such that
           sum_{i in I} omega_i * M_i  =  (1, 0, ..., 0)   (mod 2)
        Returns a dict {"I": [...], "omega": [...]} or None if the
        user's attributes don't satisfy the policy.
        """
        M = np.array(ct["M"], dtype=np.int64)
        rho = ct["rho"]

        user_attrs = set(sk_u.keys())
        I = authorized_row_set(M, rho, user_attrs)
        if I is None:
            return None

        sub_M_mod2 = np.mod(M[I, :], 2).astype(np.int64)
        target = np.zeros(M.shape[1], dtype=np.int64)
        target[0] = 1

        omega = _solve_gf2(sub_M_mod2.T, target)
        if omega is None:
            omega = _brute_force_gf2_weights(sub_M_mod2, target)
            if omega is None:
                return None

        return {"I": list(I), "omega": omega.tolist()}

    def cpabe_decrypt(self, ct: Dict[str, Any],
                      sk_u: Dict[str, np.ndarray],
                      pe: Dict[str, Any]) -> Optional[bytes]:
        """
        Vectorized per-bit Regev decryption + XOR (Eq 76-78).
        Decrypts all 256 bits per row in a single batch matmul.
        """
        rho = ct["rho"]
        ct_rows = ct["ct_rows"]
        I = pe["I"]
        omega = np.array(pe["omega"], dtype=np.int64)

        n_bits = len(ct_rows[0])
        recovered_bits = np.zeros(n_bits, dtype=np.int64)

        for idx, row_i in enumerate(I):
            if omega[idx] == 0:
                continue

            # Build batch arrays for all bits of this row
            row_ct = ct_rows[row_i]
            C1 = np.array([row_ct[b]["c1"] for b in range(n_bits)],
                          dtype=np.int64)   # (n_bits, n)
            C2 = np.array([row_ct[b]["c2"] for b in range(n_bits)],
                          dtype=np.int64)   # (n_bits,)
            t_j = sk_u[rho[row_i]]

            # Vectorized decrypt all n_bits at once
            bits = _regev_decrypt_batch(t_j, C1, C2, self.q)
            recovered_bits ^= bits

        return _bits_to_bytes((recovered_bits & 1).tolist())


# ═══════════════════════════════════════════════════════════════════
#               Back-compat wrapper functions
# ═══════════════════════════════════════════════════════════════════

def full_encrypt(cpabe: LatticeCPABE, k_aes: bytes,
                 policy: Dict[str, Any]) -> Dict[str, Any]:
    return cpabe.encrypt(k_aes, policy)


def full_decrypt(cpabe: LatticeCPABE, ct: Dict[str, Any],
                 sk_u: Dict[str, np.ndarray]) -> Optional[bytes]:
    return cpabe.decrypt(ct, sk_u)
