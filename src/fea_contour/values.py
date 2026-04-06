"""
ValueMapper — pre-computed value lookups with Z-Array caching.
Eliminates per-plot lookup overhead by pre-computing all arrays during init.
"""

import numpy as np
import pandas as pd


class ValueMapper:
    """
    Pre-computes data lookups and caches Z-arrays for instant retrieval.

    The key optimization is Z-Array Pre-Caching: heavy loop computations
    run ONCE per load case during __init__, making subsequent get_z_array()
    calls O(1) dictionary lookups.

    Parameters
    ----------
    df_gaya_lc : DataFrame
        Force/moment data for a single load case.
    mesh : MeshTopology
        Pre-built mesh topology (shared across load cases).
    """

    def __init__(self, df_gaya_lc, mesh):
        self.mesh = mesh
        self.df_nodes = df_gaya_lc[df_gaya_lc['Node'] != 'Cent'].copy()
        self.df_cent = df_gaya_lc[df_gaya_lc['Node'] == 'Cent'].copy()
        self.df_nodes['Node'] = (
            pd.to_numeric(self.df_nodes['Node'], errors='coerce')
            .fillna(0)
            .astype(int)
        )
        self.cached_z = {}
        self._build_lookups()

        # Free DataFrames after caching — no longer needed
        del self.df_nodes
        del self.df_cent

    def _build_lookups(self):
        """Build lookup dictionaries and pre-cache all Z-arrays."""
        if self.mesh.method == 'average-nodal':
            self._build_avg_nodal_cache()
        elif self.mesh.method == 'element-nodal':
            self._build_elem_nodal_cache()
        else:
            self._build_center_cache()

    def _build_avg_nodal_cache(self):
        """Average-nodal: group by node, average across elements, cache arrays."""
        numeric_cols = [
            c for c in self.df_nodes.select_dtypes(include=[np.number]).columns
            if c not in ('Node', 'Elem')
        ]
        if not numeric_cols:
            return

        grouped = self.df_nodes.groupby('Node')[numeric_cols].mean()
        avg_lookup = {c: grouped[c].to_dict() for c in numeric_cols}

        for col, col_dict in avg_lookup.items():
            z = np.zeros(len(self.mesh.x), dtype=np.float64)
            for node, idx in self.mesh.node_idx_map.items():
                val = col_dict.get(node)
                if val is not None:
                    z[idx] = val
            self.cached_z[col] = z

    def _build_elem_nodal_cache(self):
        """Element-nodal: per-element per-node values, pre-compute Z-arrays."""
        cols_to_keep = [
            c for c in self.df_nodes.select_dtypes(include=[np.number]).columns
            if c not in ('Node', 'Elem')
        ]
        if not cols_to_keep:
            return

        elem_ids = self.df_nodes['Elem'].astype(int).values
        node_ids = self.df_nodes['Node'].astype(int).values
        elem_node_lookup = {}
        for c in cols_to_keep:
            elem_node_lookup[c] = dict(zip(zip(elem_ids, node_ids), self.df_nodes[c].values))

        # HEAVY LIFTING: Pre-compute all Z-arrays (runs ONCE per LC)
        elem_ids_mesh = self.mesh.elem_ids
        node_idx_per_elem = self.mesh.node_idx_per_elem
        z = np.zeros(len(self.mesh.x), dtype=np.float64)

        for col, col_dict in elem_node_lookup.items():
            z[:] = 0.0
            for i in range(self.mesh.n_elem):
                nodes = self.mesh._get_nodes_for_elem(i)
                start_indices = node_idx_per_elem[i, :len(nodes)]
                eid = elem_ids_mesh[i]
                for j, n in enumerate(nodes):
                    val = col_dict.get((eid, n))
                    if val is not None:
                        z[start_indices[j]] = val
            self.cached_z[col] = z.copy()

    def _build_center_cache(self):
        """Element-center: centroid values per element, cache arrays."""
        numeric_cols = [
            c for c in self.df_cent.select_dtypes(include=[np.number]).columns
            if c != 'Elem'
        ]
        if not numeric_cols or len(self.df_cent) == 0:
            return

        grouped = self.df_cent.set_index('Elem')[numeric_cols]
        cent_lookup = {c: grouped[c].to_dict() for c in numeric_cols}

        for col, col_dict in cent_lookup.items():
            z = np.zeros(len(self.mesh.polygons), dtype=np.float64)
            for i, eid in enumerate(self.mesh.valid_elem_ids):
                val = col_dict.get(eid)
                if val is not None:
                    z[i] = val
            self.cached_z[col] = z

    def get_z_array(self, col):
        """
        Get pre-cached Z-array for a column. O(1) lookup.

        Returns zeros if column not found (graceful fallback).
        """
        arr = self.cached_z.get(col)
        if arr is not None:
            return arr
        # Fallback: return zeros of appropriate length
        if self.mesh.method == 'element-center':
            return np.zeros(len(self.mesh.polygons), dtype=np.float64)
        return np.zeros(len(self.mesh.x), dtype=np.float64)
