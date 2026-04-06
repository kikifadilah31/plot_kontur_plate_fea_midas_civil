"""
FEA 2D Contour Plot Generator — Entry Point
Thin wrapper that imports from the fea_contour package.

Usage:
    python plot_contur_fea.py --method average-nodal
    python plot_contur_fea.py --method all --no-mesh --comb input/kombinasi_beban.csv
"""

import sys
import os
from multiprocessing import freeze_support

# Add src/ to path so fea_contour package can be imported
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from fea_contour.cli_plot import main

if __name__ == '__main__':
    freeze_support()
    sys.exit(main())