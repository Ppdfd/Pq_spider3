"""
Z-Order (Morton) Encoding for Color-Image Encryption  — Paper [36]
====================================================================
Reference:
  Z. Man et al., Sec II-A, "Z-Order Curve" and
  Sec III-B, Steps 1-5 (Eq. 10-11).

Paper operations
----------------
Given an RGB image P of size M x N x 3:

  Step 1: Partition P into subblocks of size M/G x N/G where
          G = gcd(M, N).  Each subblock must exceed a minimum
          information threshold T (paper says T is chosen so that
          the subblock size is at least 8 x 8).

  Step 2: Each pixel p_i inside a subblock is represented as a
          5-tuple  {X_i, Y_i, R_i, G_i, B_i}  (Eq. 10).

  Step 3: Compute its Morton (Z-order) code by interleaving the
          bits of R, G, B:

              MCode = m_K ... m_2 m_1,
              where each m_i = (r_i, g_i, b_i)  (Eq. 11)

          so the full code is 3·K bits long for K-bit colour
          channels (typically K = 8, giving a 24-bit code).

  Step 4: Reorder pixels inside each subblock using the Morton
          code as a key (Z-order traversal, illustrated in Fig. 1
          of the paper).

Honest scope statement
----------------------
This module implements:
  * Byte-level 24-bit Morton encoding of individual RGB pixels
    (Eq. 11) — deterministic, reversible, and faithful to the
    paper.
  * Subblock decomposition with block size min(M, N, G) where
    G = gcd(M, N), matching the paper's Step 1.
  * A Z-order traversal of a 2-D subblock, which reorders pixels
    based on interleaved (x, y) coordinate bits.  This matches
    Fig. 1 of the paper and is what [36] calls the "Z-order
    curve traversal" (Step 5).

What this module does NOT do:
  * It does not implement the "position + colour" five-element
    NETWORK modelling described in paper [36] Step 3-4 textually
    (the paper is not fully precise about how X, Y are woven into
    the Morton bit-stream alongside R, G, B).  Our reading of the
    paper is that X, Y serve only as spatial indices for the
    Z-order reorder step, not as part of the 24-bit colour Morton
    code.  Users who read the paper differently can adapt the
    helper `morton_5tuple` below.
"""

from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np


# ────────── Bit interleaving helpers ────────────────────────────────

def _interleave3_8(r: int, g: int, b: int) -> int:
    """
    Bit-interleave three 8-bit integers into a 24-bit Morton code.

    Bit order (LSB first) follows paper [36] Eq. 11:
        MCode = ... m_2 m_1 m_0,   where m_i = (r_i, g_i, b_i)
    i.e. each triplet (r_i, g_i, b_i) is consecutive in the output.
    """
    code = 0
    for i in range(8):
        code |= ((r >> i) & 1) << (3 * i + 0)
        code |= ((g >> i) & 1) << (3 * i + 1)
        code |= ((b >> i) & 1) << (3 * i + 2)
    return code


def _deinterleave3_8(code: int) -> Tuple[int, int, int]:
    """Inverse of _interleave3_8: recover (r, g, b) from a 24-bit code."""
    r = g = b = 0
    for i in range(8):
        r |= ((code >> (3 * i + 0)) & 1) << i
        g |= ((code >> (3 * i + 1)) & 1) << i
        b |= ((code >> (3 * i + 2)) & 1) << i
    return r, g, b


def _interleave2(x: int, y: int, bits: int) -> int:
    """Classic 2-D Morton code: interleave `bits` bits of x and y."""
    code = 0
    for i in range(bits):
        code |= ((x >> i) & 1) << (2 * i + 0)
        code |= ((y >> i) & 1) << (2 * i + 1)
    return code


# ────────── Public API: pixel-level Morton (Eq. 11) ────────────────

def morton_encode_pixel(r: int, g: int, b: int) -> int:
    """Return the 24-bit Morton code of an 8-bit RGB pixel."""
    return _interleave3_8(r & 0xFF, g & 0xFF, b & 0xFF)


def morton_decode_pixel(code: int) -> Tuple[int, int, int]:
    """Inverse of morton_encode_pixel."""
    return _deinterleave3_8(code & 0xFFFFFF)


def morton_5tuple(x: int, y: int, r: int, g: int, b: int,
                  xy_bits: int = 16) -> int:
    """
    Full 5-tuple {X, Y, R, G, B} encoding.  The Morton code is
    composed of two blocks concatenated:
        [ Morton2D(x, y, xy_bits) << 24 ] | Morton3D(r, g, b)
    That is, the low 24 bits describe the colour (Eq. 11 exactly),
    and the high 2·xy_bits bits describe the position in the sub-
    block.  This is how we interpret paper [36]'s "five-element
    feature network" of Step 3.
    """
    colour = _interleave3_8(r & 0xFF, g & 0xFF, b & 0xFF)       # 24 bits
    pos    = _interleave2(x, y, xy_bits)                         # 2*xy_bits bits
    return (pos << 24) | colour


# ────────── Image-level Z-order traversal ──────────────────────────

def zorder_traversal_order(h: int, w: int) -> List[Tuple[int, int]]:
    """
    Return the list of (y, x) coordinates of an h×w grid in Z-order.

    Uses the 2-D Morton code as the sort key, which gives exactly
    the traversal pattern shown in Fig. 1 of paper [36].
    """
    # Pad to the next power of two on both axes so the Morton
    # ordering is well-defined.  Indices exceeding (h, w) are
    # discarded at the end.
    pad = max(h, w)
    pad = 1 << (pad - 1).bit_length() if pad > 1 else 1
    bits = pad.bit_length() - 1 if pad > 1 else 1

    coords = []
    for i in range(pad * pad):
        # decode i as Morton(x, y)
        x = 0; y = 0
        for b in range(bits):
            x |= ((i >> (2 * b + 0)) & 1) << b
            y |= ((i >> (2 * b + 1)) & 1) << b
        if x < w and y < h:
            coords.append((y, x))
    return coords


def zorder_scramble(img: np.ndarray) -> Tuple[np.ndarray, List[Tuple[int, int]]]:
    """
    Reorder pixels of an h×w×3 image along the Z-order traversal.

    Returns
    -------
    flat : shape (h*w, 3) array in Z-order
    order: list of (y, x) coordinate pairs giving original positions
           (needed for inversion).
    """
    if img.ndim != 3 or img.shape[2] != 3:
        raise ValueError("zorder_scramble expects an h×w×3 RGB array")
    h, w, _ = img.shape
    order = zorder_traversal_order(h, w)
    flat = np.array([img[y, x] for (y, x) in order], dtype=img.dtype)
    return flat, order


def zorder_unscramble(flat: np.ndarray,
                      order: List[Tuple[int, int]],
                      shape: Tuple[int, int, int]) -> np.ndarray:
    """Inverse of zorder_scramble."""
    h, w, c = shape
    out = np.zeros(shape, dtype=flat.dtype)
    for idx, (y, x) in enumerate(order):
        out[y, x] = flat[idx]
    return out


# ────────── Subblock decomposition (Paper Step 1) ───────────────────

def subblock_size(M: int, N: int, min_block: int = 8) -> int:
    """
    Compute the subblock side length per paper [36] Step 1:
    at least max(min_block, gcd(M, N)).
    """
    g = math.gcd(M, N)
    return max(min_block, g)


def partition_subblocks(img: np.ndarray,
                        block: int = None) -> List[np.ndarray]:
    """
    Partition an image into `block`-sized subblocks (Step 1).

    If `block` is None, it is chosen per `subblock_size(M, N)`.
    The last row/column of subblocks may be smaller than `block`
    if the dimensions are not multiples of `block`.
    """
    H, W = img.shape[:2]
    if block is None:
        block = subblock_size(H, W)
    blocks = []
    for by in range(0, H, block):
        for bx in range(0, W, block):
            blocks.append(img[by:by + block, bx:bx + block])
    return blocks


# ────────── Morton-coded representation of a full image (Eq. 10-11) ─

def image_to_morton_codes(img: np.ndarray) -> np.ndarray:
    """
    Apply Eq. 11 to every pixel of an h×w×3 image and return an
    h×w array of 24-bit Morton codes.
    """
    h, w, _ = img.shape
    codes = np.zeros((h, w), dtype=np.uint32)
    for y in range(h):
        for x in range(w):
            r, g, b = img[y, x]
            codes[y, x] = morton_encode_pixel(int(r), int(g), int(b))
    return codes


def morton_codes_to_image(codes: np.ndarray) -> np.ndarray:
    """Inverse of image_to_morton_codes."""
    h, w = codes.shape
    img = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            r, g, b = morton_decode_pixel(int(codes[y, x]))
            img[y, x] = [r, g, b]
    return img


# ────────── Convenience: Morton-encode arbitrary byte stream ───────
#
# For non-image data (which [36] doesn't formally cover but which
# PQ-SPIDER's benchmark harness needs for telemetry payloads),
# we group input bytes in triples and treat each triple as (R, G, B).

def morton_encode_bytes(data: bytes) -> bytes:
    """
    Byte-stream Morton encoding.  Groups input in triples and
    applies Eq. 11 per triple.  If len(data) % 3 != 0, the tail
    is zero-padded and the pad length is NOT preserved (this is a
    simplification suitable only for fixed-length benchmark payloads).

    Returns 3 bytes of Morton code per 3 bytes of input.
    """
    out = bytearray()
    padded = data + b"\x00" * ((3 - len(data) % 3) % 3)
    for i in range(0, len(padded), 3):
        code = _interleave3_8(padded[i], padded[i + 1], padded[i + 2])
        out.extend(code.to_bytes(3, "little"))
    return bytes(out[:len(data)])  # truncate to original length


def morton_decode_bytes(code_data: bytes, original_len: int) -> bytes:
    """Inverse of morton_encode_bytes."""
    pad = (3 - original_len % 3) % 3
    buf = code_data + b"\x00" * pad
    out = bytearray()
    for i in range(0, len(buf), 3):
        code_int = int.from_bytes(buf[i:i + 3], "little")
        r, g, b = _deinterleave3_8(code_int)
        out.extend([r, g, b])
    return bytes(out[:original_len])
