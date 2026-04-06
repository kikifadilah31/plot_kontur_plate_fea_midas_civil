"""
FEA Results Report Generator — Entry Point
Thin wrapper that imports from the fea_contour package.

Usage:
    python generate_reports.py --master
    python generate_reports.py --comb --master --thickness 0.5
"""

import sys
import os

# Add src/ to path so fea_contour package can be imported
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from fea_contour.cli_report import main

if __name__ == '__main__':
    sys.exit(main())