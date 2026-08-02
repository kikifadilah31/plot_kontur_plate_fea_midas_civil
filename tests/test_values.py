"""
ValueMapper Z-array caching, focused on the element-nodal path that indexed
node_idx_per_elem without checking whether the element survived mesh building
(A2).
"""

import numpy as np
import pandas as pd
import pytest

from shell_kit.mesh import MeshTopology
from shell_kit.values import ValueMapper

COL = 'Mxx (kN·m/m)'


@pytest.fixture
def coords():
    return {
        1: {'X': 0.0, 'Y': 0.0},
        2: {'X': 1.0, 'Y': 0.0},
        3: {'X': 1.0, 'Y': 1.0},
        4: {'X': 0.0, 'Y': 1.0},
        5: {'X': 2.0, 'Y': 0.0},
    }


@pytest.fixture
def conn_with_orphan():
    return pd.DataFrame({
        'iEL': [101, 102],
        '1': [1, 2],
        '2': [2, 5],
        '3': [3, 99],   # node 99 has no coordinates
        '4': [4, 3],
    })


@pytest.fixture
def gaya():
    """Element 101 has moment 10.0 everywhere; orphan 102 has a huge value."""
    rows = []
    for node in (1, 2, 3, 4):
        rows.append({'Elem': 101, 'Load': 'MS', 'Node': node, COL: 10.0})
    for node in (2, 5, 99, 3):
        rows.append({'Elem': 102, 'Load': 'MS', 'Node': node, COL: 9999.0})
    rows.append({'Elem': 101, 'Load': 'MS', 'Node': 'Cent', COL: 10.0})
    rows.append({'Elem': 102, 'Load': 'MS', 'Node': 'Cent', COL: 9999.0})
    return pd.DataFrame(rows)


def test_element_nodal_ignores_orphan_element(conn_with_orphan, coords, gaya):
    mesh = MeshTopology(conn_with_orphan, coords, 'element-nodal')
    vm = ValueMapper(gaya, mesh)
    z = vm.get_z_array(COL)

    assert len(z) == len(mesh.x)
    # The orphan's 9999.0 must not have leaked into any node
    assert np.all(z == 10.0)


def test_element_center_ignores_orphan_element(conn_with_orphan, coords, gaya):
    mesh = MeshTopology(conn_with_orphan, coords, 'element-center')
    vm = ValueMapper(gaya, mesh)
    z = vm.get_z_array(COL)

    assert len(z) == 1
    assert z[0] == 10.0


def test_average_nodal_ignores_orphan_element(conn_with_orphan, coords, gaya):
    """
    Nodes 2 and 3 are shared with the dropped element. Averaging must exclude
    its rows entirely — mixing them in would drag the shared nodes toward a
    value from geometry that is not even in the mesh.
    """
    mesh = MeshTopology(conn_with_orphan, coords, 'average-nodal')
    vm = ValueMapper(gaya, mesh)
    z = vm.get_z_array(COL)

    assert len(z) == len(mesh.x)
    assert np.all(z == 10.0)


def test_missing_column_falls_back_to_zeros(conn_with_orphan, coords, gaya):
    mesh = MeshTopology(conn_with_orphan, coords, 'element-nodal')
    vm = ValueMapper(gaya, mesh)
    z = vm.get_z_array('Vxx (kN/m)')
    assert len(z) == len(mesh.x)
    assert np.all(z == 0.0)
