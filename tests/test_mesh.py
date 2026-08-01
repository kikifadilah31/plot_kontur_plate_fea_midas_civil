"""
Mesh topology, focused on elements whose connectivity references a node that
has no coordinates (A2).

node_idx_per_elem used to be np.empty and only filled for valid elements, so
ValueMapper read uninitialised memory and scattered values into random nodes.
"""

import numpy as np
import pandas as pd
import pytest

from fea_contour.mesh import MeshTopology

METHODS = ['average-nodal', 'element-nodal', 'element-center']


@pytest.fixture
def coords():
    """Unit grid of 6 nodes — node 99 deliberately absent."""
    return {
        1: {'X': 0.0, 'Y': 0.0},
        2: {'X': 1.0, 'Y': 0.0},
        3: {'X': 1.0, 'Y': 1.0},
        4: {'X': 0.0, 'Y': 1.0},
        5: {'X': 2.0, 'Y': 0.0},
        6: {'X': 2.0, 'Y': 1.0},
    }


@pytest.fixture
def conn_with_orphan():
    """Element 101 is fine; element 102 references the missing node 99."""
    return pd.DataFrame({
        'iEL': [101, 102],
        '1': [1, 2],
        '2': [2, 5],
        '3': [3, 99],
        '4': [4, 3],
    })


@pytest.fixture
def conn_all_valid():
    return pd.DataFrame({
        'iEL': [101, 102],
        '1': [1, 2],
        '2': [2, 5],
        '3': [3, 6],
        '4': [4, 3],
    })


@pytest.mark.parametrize('method', METHODS)
def test_orphan_element_is_marked_invalid(conn_with_orphan, coords, method):
    mesh = MeshTopology(conn_with_orphan, coords, method)
    assert mesh.valid_mask.tolist() == [True, False]
    assert mesh.n_invalid == 1


@pytest.mark.parametrize('method', METHODS)
def test_all_valid_mesh_reports_none_invalid(conn_all_valid, coords, method):
    mesh = MeshTopology(conn_all_valid, coords, method)
    assert mesh.valid_mask.all()
    assert mesh.n_invalid == 0


def test_skipped_element_has_no_garbage_indices(conn_with_orphan, coords):
    """
    The heart of the bug: every slot for a skipped element must be an
    unmistakable sentinel, never a plausible-looking index.
    """
    mesh = MeshTopology(conn_with_orphan, coords, 'element-nodal')
    assert (mesh.node_idx_per_elem[1] == -1).all()

    # Valid element's indices must all address real coordinate slots
    valid_rows = mesh.node_idx_per_elem[0]
    used = valid_rows[valid_rows >= 0]
    assert used.size == 4
    assert used.max() < len(mesh.x)


def test_element_center_valid_ids_match_mask(conn_with_orphan, coords):
    mesh = MeshTopology(conn_with_orphan, coords, 'element-center')
    assert mesh.valid_elem_ids.tolist() == [101]
    assert len(mesh.polygons) == 1
    assert len(mesh.centroids) == 1


def test_average_nodal_only_uses_nodes_from_valid_elements(conn_with_orphan, coords):
    mesh = MeshTopology(conn_with_orphan, coords, 'average-nodal')
    # Only nodes 1,2,3,4 belong to the surviving element
    assert mesh.unique_nodes == [1, 2, 3, 4]
    assert len(mesh.x) == 4


def test_triangle_indices_stay_in_range(conn_with_orphan, coords):
    for method in ('average-nodal', 'element-nodal'):
        mesh = MeshTopology(conn_with_orphan, coords, method)
        assert mesh.triangles.min() >= 0
        assert mesh.triangles.max() < len(mesh.x)
