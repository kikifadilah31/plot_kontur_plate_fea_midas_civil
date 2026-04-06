"""
MeshTopology — pre-computed mesh structure.
Computed ONCE per contour method, reused for all load cases and columns.
"""

import numpy as np


class MeshTopology:
    """
    Pre-computes the geometric mesh structure for contour plotting.

    Depending on the contour method, builds:
      - average-nodal: shared-node triangulation (smooth contours)
      - element-nodal: disconnected triangulation (raw/discontinuous)
      - element-center: polygon collection (blocky, per-element)

    This object is IMMUTABLE after construction and should be built
    ONCE per method, then shared across all load cases.
    """

    def __init__(self, df_conn, coord_dict, contour_method):
        self.method = contour_method
        self.coord_dict = coord_dict
        self.elem_ids = df_conn['iEL'].values.astype(int)
        self.n1 = df_conn['1'].values.astype(int)
        self.n2 = df_conn['2'].values.astype(int)
        self.n3 = df_conn['3'].values.astype(int)
        self.n4 = df_conn['4'].values.astype(int)
        self.is_quad = (self.n4 != 0) & (self.n4 != self.n3)
        self.n_elem = len(self.elem_ids)
        self._build_topology()

    def _get_nodes_for_elem(self, idx):
        """Return list of node IDs for element at index idx."""
        if self.is_quad[idx]:
            return [self.n1[idx], self.n2[idx], self.n3[idx], self.n4[idx]]
        return [self.n1[idx], self.n2[idx], self.n3[idx]]

    def _build_topology(self):
        """Dispatch to the appropriate topology builder."""
        if self.method in ('average-nodal', 'element-nodal'):
            self._build_triangle_topology()
        else:
            self._build_polygon_topology()

    def _build_triangle_topology(self):
        """Pre-allocate triangle arrays and dispatch to shared/disconnected builder."""
        n_tri = np.sum(self.is_quad) * 2 + np.sum(~self.is_quad)
        self.triangles = np.empty((n_tri, 3), dtype=np.int32)
        if self.method == 'average-nodal':
            self._build_shared_node_mesh(n_tri)
        else:
            self._build_disconnected_mesh(n_tri)

    def _build_shared_node_mesh(self, n_tri):
        """Build shared-node mesh for average-nodal method (smooth contours)."""
        unique_nodes = set()
        for i in range(self.n_elem):
            nodes = self._get_nodes_for_elem(i)
            if all(n in self.coord_dict for n in nodes):
                unique_nodes.update(nodes)

        self.unique_nodes = sorted(unique_nodes)
        self.node_idx_map = {n: i for i, n in enumerate(self.unique_nodes)}
        self.x = np.empty(len(self.unique_nodes), dtype=np.float64)
        self.y = np.empty(len(self.unique_nodes), dtype=np.float64)

        for n in self.unique_nodes:
            idx = self.node_idx_map[n]
            self.x[idx] = self.coord_dict[n]['X']
            self.y[idx] = self.coord_dict[n]['Y']

        tri_idx = 0
        for i in range(self.n_elem):
            nodes = self._get_nodes_for_elem(i)
            if all(n in self.coord_dict for n in nodes):
                if self.is_quad[i]:
                    self.triangles[tri_idx] = [
                        self.node_idx_map[nodes[0]],
                        self.node_idx_map[nodes[1]],
                        self.node_idx_map[nodes[2]],
                    ]
                    self.triangles[tri_idx + 1] = [
                        self.node_idx_map[nodes[0]],
                        self.node_idx_map[nodes[2]],
                        self.node_idx_map[nodes[3]],
                    ]
                    tri_idx += 2
                else:
                    self.triangles[tri_idx] = [
                        self.node_idx_map[nodes[0]],
                        self.node_idx_map[nodes[1]],
                        self.node_idx_map[nodes[2]],
                    ]
                    tri_idx += 1
        self.triangles = self.triangles[:tri_idx]

    def _build_disconnected_mesh(self, n_tri):
        """Build disconnected mesh for element-nodal method (raw/discontinuous)."""
        nodes_per_elem = np.where(self.is_quad, 4, 3)
        total_nodes = np.sum(nodes_per_elem)
        self.x = np.empty(total_nodes, dtype=np.float64)
        self.y = np.empty(total_nodes, dtype=np.float64)
        self.node_idx_per_elem = np.empty((self.n_elem, 4), dtype=np.int32)

        node_idx = tri_idx = 0
        for i in range(self.n_elem):
            nodes = self._get_nodes_for_elem(i)
            if all(n in self.coord_dict for n in nodes):
                start_idx = node_idx
                for n in nodes:
                    self.x[node_idx] = self.coord_dict[n]['X']
                    self.y[node_idx] = self.coord_dict[n]['Y']
                    node_idx += 1
                if self.is_quad[i]:
                    self.triangles[tri_idx] = [start_idx, start_idx + 1, start_idx + 2]
                    self.triangles[tri_idx + 1] = [start_idx, start_idx + 2, start_idx + 3]
                    tri_idx += 2
                else:
                    self.triangles[tri_idx] = [start_idx, start_idx + 1, start_idx + 2]
                    tri_idx += 1
                self.node_idx_per_elem[i, :len(nodes)] = range(start_idx, start_idx + len(nodes))

        self.x = self.x[:node_idx]
        self.y = self.y[:node_idx]
        self.triangles = self.triangles[:tri_idx]

    def _build_polygon_topology(self):
        """Build polygon topology for element-center method (blocky contours)."""
        self.polygons = []
        self.centroids = []
        self.valid_elem_indices = []

        for i in range(self.n_elem):
            nodes = self._get_nodes_for_elem(i)
            if all(n in self.coord_dict for n in nodes):
                poly = [(self.coord_dict[n]['X'], self.coord_dict[n]['Y']) for n in nodes]
                self.polygons.append(poly)
                self.centroids.append((
                    sum(p[0] for p in poly) / len(poly),
                    sum(p[1] for p in poly) / len(poly),
                ))
                self.valid_elem_indices.append(i)

        self.valid_elem_ids = self.elem_ids[self.valid_elem_indices]
