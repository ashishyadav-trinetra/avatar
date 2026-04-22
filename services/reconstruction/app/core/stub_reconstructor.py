"""
Stub reconstructor for DEV MODE — generates a simple FLAME-topology GLB
with morph targets so the full pipeline can be tested without GPU/MICA/DECA.

The mesh is a crude head-shaped ellipsoid with the correct vertex count
and all 56 morph targets (expression + jaw) present but synthetically generated.
"""

import hashlib
import logging
import time
from typing import Dict

import numpy as np
import trimesh

from .base import ReconstructionInput, ReconstructionModel, ReconstructionOutput

logger = logging.getLogger(__name__)

# FLAME has 5023 vertices, 9976 faces
_FLAME_V = 5023
_FLAME_F = 9976
_NUM_BLENDSHAPES = 56  # 50 expression + 6 jaw


def _generate_head_mesh() -> trimesh.Trimesh:
    """
    Generate a head-shaped ellipsoid mesh with FLAME-like vertex count.
    Not anatomically accurate — just enough geometry to test the pipeline.
    """
    # Create a UV sphere and scale to head-like proportions
    sphere = trimesh.creation.icosphere(subdivisions=5)

    # Scale to head proportions (slightly taller than wide)
    vertices = sphere.vertices.copy()
    vertices[:, 0] *= 0.08   # width ~16cm
    vertices[:, 1] *= 0.115  # height ~23cm
    vertices[:, 2] *= 0.10   # depth ~20cm

    # Shift up so neck is at origin
    vertices[:, 1] += 0.05

    # Resample to exact FLAME vertex count if needed
    # icosphere(5) gives 10242 verts — we need to subsample
    if len(vertices) > _FLAME_V:
        indices = np.linspace(0, len(vertices) - 1, _FLAME_V, dtype=int)
        vertices = vertices[indices]

    # Generate faces for the subsampled vertices using Delaunay-like approach
    # For the stub, we'll use a simple triangle strip pattern
    faces = []
    # Create a rough triangulation
    n = len(vertices)
    # Sort by y then by angle around y-axis for reasonable triangulation
    angles = np.arctan2(vertices[:, 2], vertices[:, 0])
    y_vals = vertices[:, 1]

    # Group into rings by y-coordinate
    n_rings = 80
    ring_size = n // n_rings
    for ring in range(n_rings - 1):
        start_a = ring * ring_size
        start_b = (ring + 1) * ring_size
        for i in range(ring_size - 1):
            a = start_a + i
            b = start_a + i + 1
            c = start_b + i
            d = start_b + i + 1
            if a < n and b < n and c < n and d < n:
                faces.append([a, b, c])
                faces.append([b, d, c])

    faces = np.array(faces[:_FLAME_F]) if len(faces) >= _FLAME_F else np.array(faces)

    mesh = trimesh.Trimesh(vertices=vertices[:_FLAME_V], faces=faces, process=False)
    return mesh


def _generate_morph_targets(base_vertices: np.ndarray) -> Dict[str, np.ndarray]:
    """
    Generate synthetic morph targets (blendshapes).
    Each is a small displacement from the base pose.
    """
    rng = np.random.RandomState(42)  # Deterministic for reproducibility
    targets = {}

    # 50 expression params — mostly affect lower face / cheeks / forehead
    for i in range(50):
        displacement = rng.randn(*base_vertices.shape).astype(np.float32) * 0.002
        # Bias mouth area (lower y vertices) for first 20 params (lip-related)
        if i < 20:
            mouth_mask = (base_vertices[:, 1] < 0.03).astype(np.float32)
            displacement *= mouth_mask[:, np.newaxis] * 3 + 0.3
        targets[f"exp_{i}"] = displacement

    # 6 jaw params — mainly rotate/translate the jaw
    for i in range(6):
        displacement = np.zeros_like(base_vertices, dtype=np.float32)
        jaw_mask = (base_vertices[:, 1] < 0.0).astype(np.float32)
        if i == 0:  # Primary jaw open
            displacement[:, 1] = -jaw_mask * 0.01
        elif i == 1:  # Jaw forward
            displacement[:, 2] = jaw_mask * 0.005
        else:  # Minor jaw adjustments
            displacement[:, i % 3] = jaw_mask * rng.randn(len(base_vertices)).astype(np.float32) * 0.002
        targets[f"jaw_{i}"] = displacement

    return targets


def _generate_texture(resolution: int = 1024) -> np.ndarray:
    """Generate a simple skin-colored texture map."""
    texture = np.full((resolution, resolution, 3), [210, 180, 160], dtype=np.uint8)

    # Add some subtle variation
    rng = np.random.RandomState(42)
    noise = rng.randint(-10, 10, texture.shape, dtype=np.int16)
    texture = np.clip(texture.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    return texture


class StubReconstructor(ReconstructionModel):
    """
    Dev-mode stub — produces a valid GLB with FLAME topology
    and morph targets, without any real reconstruction.
    """

    name = "stub"

    def __init__(self):
        self._ready = False
        self._base_mesh = None
        self._morph_targets = None

    async def initialize(self, model_dir: str, device: str) -> None:
        logger.info("StubReconstructor: generating placeholder mesh...")
        t0 = time.monotonic()

        self._base_mesh = _generate_head_mesh()
        self._morph_targets = _generate_morph_targets(self._base_mesh.vertices)

        elapsed = (time.monotonic() - t0) * 1000
        logger.info(
            f"StubReconstructor ready — {len(self._base_mesh.vertices)} verts, "
            f"{len(self._base_mesh.faces)} faces, "
            f"{len(self._morph_targets)} morph targets — {elapsed:.0f}ms"
        )
        self._ready = True

    async def reconstruct(self, input: ReconstructionInput) -> ReconstructionOutput:
        if not self._ready:
            raise RuntimeError("StubReconstructor not initialized")

        t0 = time.monotonic()

        # Build a GLB scene with morph targets
        # trimesh doesn't natively support morph targets in GLB export,
        # so we embed them as custom extras and use a thin GLTF builder.
        glb_data = self._export_glb_with_morphs()

        checksum = "sha256:" + hashlib.sha256(glb_data).hexdigest()
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        logger.info(
            f"Stub reconstruction for {input.session_id}: "
            f"{len(glb_data)} bytes GLB, {elapsed_ms}ms"
        )

        return ReconstructionOutput(
            session_id=input.session_id,
            glb_data=glb_data,
            texture_data=None,
            vertex_count=len(self._base_mesh.vertices),
            face_count=len(self._base_mesh.faces),
            blendshape_count=len(self._morph_targets),
            mesh_version="0.1.0-stub",
            texture_version="0.1.0-stub",
            checksum=checksum,
            reconstruction_time_ms=elapsed_ms,
            model_name=self.name,
        )

    def _export_glb_with_morphs(self) -> bytes:
        """
        Export mesh as GLB with morph targets embedded.
        Uses trimesh's GLTF export with manually injected morph target data.
        """
        import io
        import json
        import struct

        vertices = self._base_mesh.vertices.astype(np.float32)
        faces = self._base_mesh.faces.astype(np.uint32)
        n_verts = len(vertices)
        n_faces = len(faces)

        # ── Build binary buffer ──────────────────────────────
        buffer_data = io.BytesIO()

        # Vertex positions
        pos_offset = buffer_data.tell()
        buffer_data.write(vertices.tobytes())
        pos_length = buffer_data.tell() - pos_offset

        # Face indices
        idx_offset = buffer_data.tell()
        buffer_data.write(faces.tobytes())
        idx_length = buffer_data.tell() - idx_offset

        # Morph target displacements
        morph_views = []
        target_names = sorted(self._morph_targets.keys(),
                              key=lambda k: (k.split('_')[0], int(k.split('_')[1])))

        for name in target_names:
            disp = self._morph_targets[name].astype(np.float32)
            # Ensure correct vertex count
            if len(disp) < n_verts:
                padded = np.zeros((n_verts, 3), dtype=np.float32)
                padded[:len(disp)] = disp
                disp = padded
            elif len(disp) > n_verts:
                disp = disp[:n_verts]

            offset = buffer_data.tell()
            buffer_data.write(disp.tobytes())
            length = buffer_data.tell() - offset
            morph_views.append({
                "offset": offset,
                "length": length,
                "min": disp.min(axis=0).tolist(),
                "max": disp.max(axis=0).tolist(),
            })

        raw_buffer = buffer_data.getvalue()

        # Pad buffer to 4-byte alignment
        while len(raw_buffer) % 4 != 0:
            raw_buffer += b'\x00'

        # ── Build GLTF JSON ──────────────────────────────────
        accessors = []
        buffer_views = []

        # Buffer view 0: vertex positions
        buffer_views.append({
            "buffer": 0,
            "byteOffset": pos_offset,
            "byteLength": pos_length,
            "target": 34962,  # ARRAY_BUFFER
        })
        # Accessor 0: positions
        v_min = vertices.min(axis=0).tolist()
        v_max = vertices.max(axis=0).tolist()
        accessors.append({
            "bufferView": 0,
            "componentType": 5126,  # FLOAT
            "count": n_verts,
            "type": "VEC3",
            "min": v_min,
            "max": v_max,
        })

        # Buffer view 1: indices
        buffer_views.append({
            "buffer": 0,
            "byteOffset": idx_offset,
            "byteLength": idx_length,
            "target": 34963,  # ELEMENT_ARRAY_BUFFER
        })
        # Accessor 1: indices
        accessors.append({
            "bufferView": 1,
            "componentType": 5125,  # UNSIGNED_INT
            "count": n_faces * 3,
            "type": "SCALAR",
            "min": [0],
            "max": [n_verts - 1],
        })

        # Morph target buffer views and accessors
        morph_accessor_start = len(accessors)
        targets_list = []

        for i, mv in enumerate(morph_views):
            bv_idx = len(buffer_views)
            buffer_views.append({
                "buffer": 0,
                "byteOffset": mv["offset"],
                "byteLength": mv["length"],
                "target": 34962,
            })
            acc_idx = len(accessors)
            accessors.append({
                "bufferView": bv_idx,
                "componentType": 5126,
                "count": n_verts,
                "type": "VEC3",
                "min": mv["min"],
                "max": mv["max"],
            })
            targets_list.append({"POSITION": acc_idx})

        # ── Assemble GLTF document ───────────────────────────
        gltf = {
            "asset": {
                "version": "2.0",
                "generator": "avatar-reconstruction-stub",
            },
            "scene": 0,
            "scenes": [{"nodes": [0]}],
            "nodes": [{"mesh": 0, "name": "AvatarHead"}],
            "meshes": [{
                "primitives": [{
                    "attributes": {"POSITION": 0},
                    "indices": 1,
                    "targets": targets_list,
                }],
                "extras": {
                    "targetNames": target_names,
                },
                "weights": [0.0] * len(target_names),
            }],
            "accessors": accessors,
            "bufferViews": buffer_views,
            "buffers": [{"byteLength": len(raw_buffer)}],
        }

        # ── Pack as GLB ──────────────────────────────────────
        gltf_json = json.dumps(gltf, separators=(',', ':')).encode('utf-8')
        # Pad JSON to 4-byte alignment
        while len(gltf_json) % 4 != 0:
            gltf_json += b' '

        # GLB header
        glb = io.BytesIO()
        # Magic
        glb.write(b'glTF')
        # Version
        glb.write(struct.pack('<I', 2))
        # Total length (header + JSON chunk + binary chunk)
        total = 12 + (8 + len(gltf_json)) + (8 + len(raw_buffer))
        glb.write(struct.pack('<I', total))

        # JSON chunk
        glb.write(struct.pack('<I', len(gltf_json)))
        glb.write(b'JSON')
        glb.write(gltf_json)

        # Binary chunk
        glb.write(struct.pack('<I', len(raw_buffer)))
        glb.write(b'BIN\x00')
        glb.write(raw_buffer)

        return glb.getvalue()

    def is_ready(self) -> bool:
        return self._ready
