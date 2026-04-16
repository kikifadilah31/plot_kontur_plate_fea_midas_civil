"""
FEA Contour Plotter — Streamlit Web UI.

Interactive dashboard with 3 tabs:
  1. Contour Plot (Plotly interactive + Matplotlib save)
  2. Report (Markdown / Typst)
  3. Rebar Analysis (Plotly interactive)
"""

import streamlit as st
import pandas as pd
import numpy as np
import os
import tempfile
from datetime import datetime

from fea_contour.config import (
    DEFAULT_THICKNESS, ALL_METHODS, FORCE_COLUMNS,
    STRESS_COLUMNS, PLOTTABLE_COLUMNS, STRESS_PAIRS,
    OUTPUT_FOLDER,
)
from fea_contour.math_utils import calculate_stress_vectorized, safe_filename
from fea_contour.io_utils import build_coord_dict
from fea_contour.mesh import MeshTopology
from fea_contour.values import ValueMapper
from fea_contour.combination import parse_combination_file, validate_combinations
from fea_contour.reporting import (
    extract_statistics, compute_master_envelope,
    render_report_md, render_master_md,
)
from fea_contour.reporting_typst import render_report_typst, render_master_typst
from fea_contour.rebar import (
    DEFAULT_FC, DEFAULT_FY, DEFAULT_COVER,
    AVAILABLE_DIAMETERS, SHEAR_DIAMETERS,
    calc_effective_depth, calc_as_required,
    calc_spacing_from_diameter, calc_diameter_from_spacing,
    calc_shear_Av_per_s, calc_shear_diameter,
)
from fea_contour.plotting_plotly import (
    generate_contour_plotly, generate_rebar_plotly,
)
from fea_contour.plotting import init_worker, generate_plot_worker
from fea_contour.plotting_rebar import init_rebar_worker, generate_rebar_plot_worker


# =============================================================================
# Page Configuration
# =============================================================================
st.set_page_config(
    page_title="FEA Contour Plotter",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📊 FEA Contour Plotter")
st.caption("Professional FEA Visualization, Reporting & Rebar Analysis Dashboard")


# =============================================================================
# Sidebar — File Uploads & Common Parameters
# =============================================================================
with st.sidebar:
    st.header("📂 Input Files")
    coord_file = st.file_uploader("Koordinat CSV", type='csv', key='coord')
    conn_file = st.file_uploader("Connectivity CSV", type='csv', key='conn')
    gaya_file = st.file_uploader("Gaya/Momen CSV", type='csv', key='gaya')
    comb_file = st.file_uploader(
        "Kombinasi CSV *(opsional)*", type='csv', key='comb',
    )

    st.divider()
    st.header("🔧 Common Parameters")
    thickness = st.number_input(
        "Thickness (m)", value=DEFAULT_THICKNESS,
        min_value=0.05, step=0.05, format="%.3f",
    )
    method = st.selectbox("Contour Method", ALL_METHODS)


# =============================================================================
# Data Loading (with caching)
# =============================================================================
if not all([coord_file, conn_file, gaya_file]):
    st.info(
        "👆 Upload the **3 required CSV files** "
        "(Koordinat, Connectivity, Gaya) in the sidebar to get started."
    )
    st.stop()


@st.cache_data(show_spinner=False)
def _load_dataframes(coord_bytes, conn_bytes, gaya_bytes):
    """Load and return DataFrames from uploaded CSV files."""
    df_k = pd.read_csv(coord_bytes, low_memory=False)
    df_c = pd.read_csv(conn_bytes, low_memory=False)
    df_g = pd.read_csv(gaya_bytes, low_memory=False)
    for df in [df_k, df_c, df_g]:
        df.columns = df.columns.str.strip()
    return df_k, df_c, df_g


with st.spinner("Loading CSV files..."):
    df_kordinat, df_conn, df_gaya = _load_dataframes(
        coord_file, conn_file, gaya_file,
    )

coord_dict = build_coord_dict(df_kordinat)
load_cases = sorted([
    str(lc).strip()
    for lc in df_gaya['Load'].dropna().unique()
    if str(lc).strip()
])


# =============================================================================
# Build Mesh & Value Mappers (session_state for mutable objects)
# =============================================================================
def _rebuild_data(method_key):
    """Rebuild mesh and value mappers when method changes."""
    mesh = MeshTopology(df_conn, coord_dict, method_key)
    vm_cache = {}
    for lc in load_cases:
        df_lc = df_gaya[df_gaya['Load'] == lc].copy()
        vm_cache[lc] = ValueMapper(df_lc, mesh)
    return mesh, vm_cache


cache_key = f"{method}_{id(df_conn)}"
if st.session_state.get('_cache_key') != cache_key:
    with st.spinner(f"Building {method} mesh & value mappers..."):
        mesh, vm_cache = _rebuild_data(method)
        st.session_state.mesh = mesh
        st.session_state.vm_cache = vm_cache
        st.session_state._cache_key = cache_key
else:
    mesh = st.session_state.mesh
    vm_cache = st.session_state.vm_cache


# =============================================================================
# Parse Combinations
# =============================================================================
combos = []
if comb_file is not None:
    # Save uploaded file to temp then parse (parse_combination_file needs path)
    with tempfile.NamedTemporaryFile(
        delete=False, suffix='.csv', mode='wb',
    ) as tmp:
        tmp.write(comb_file.getvalue())
        tmp_path = tmp.name

    combos_raw = parse_combination_file(tmp_path)
    os.unlink(tmp_path)

    _, matched_map = validate_combinations(combos_raw, set(load_cases))
    for combo in combos_raw:
        resolved = []
        valid = True
        for lc, fac in combo['lc_factors']:
            actual = matched_map.get(lc, lc)
            if actual in vm_cache:
                resolved.append((actual, fac))
            else:
                valid = False
                break
        if valid and resolved:
            combos.append({'name': combo['name'], 'lc_factors': resolved})

# Sidebar status
with st.sidebar:
    st.divider()
    st.success(
        f"**{len(load_cases)}** Load Cases | "
        f"**{len(df_kordinat):,}** Nodes"
    )
    if combos:
        st.info(f"**{len(combos)}** Valid Combinations")


# =============================================================================
# Helper: Get column arrays for a source
# =============================================================================
def _get_arrays_for_source(source_name, is_combo=False):
    """Get force/moment Z-arrays for a source (LC or combination)."""
    arrays = {}
    if is_combo:
        combo = next(c for c in combos if c['name'] == source_name)
        ref_lc = combo['lc_factors'][0][0]
        for col in FORCE_COLUMNS:
            z = np.zeros_like(vm_cache[ref_lc].get_z_array(col))
            for lc, fac in combo['lc_factors']:
                z += fac * vm_cache[lc].get_z_array(col)
            if not np.all(z == 0):
                arrays[col] = z
    else:
        vm = vm_cache[source_name]
        for col in FORCE_COLUMNS:
            z = vm.get_z_array(col)
            if not np.all(z == 0):
                arrays[col] = z
    return arrays


def _add_stress_arrays(arrays, thickness_val):
    """Compute and add stress arrays in-place."""
    stress_cache = {}
    for stress_col, (force_col, moment_col) in STRESS_PAIRS.items():
        f_arr = arrays.get(force_col)
        m_arr = arrays.get(moment_col)
        if f_arr is None or m_arr is None:
            continue
        pair = (force_col, moment_col)
        if pair not in stress_cache:
            top, bot = calculate_stress_vectorized(f_arr, m_arr, thickness_val)
            stress_cache[pair] = (top, bot)
        top, bot = stress_cache[pair]
        arrays[stress_col] = top if 'Top' in stress_col else bot


# =============================================================================
# Tabs
# =============================================================================
tab_plot, tab_report, tab_rebar = st.tabs([
    "📊 Contour Plot", "📋 Report", "🧮 Rebar Analysis",
])


# ─────────────── TAB 1: Contour Plot ───────────────
with tab_plot:
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        output_mode = st.radio(
            "Output Mode",
            ["Display Only", "Save Only", "Display & Save"],
            key='plot_output_mode',
        )
    with col_b:
        theme = st.selectbox("Theme", ['light', 'dark'], key='plot_theme')
    with col_c:
        show_mesh = not st.checkbox("Hide Mesh Wireframe", value=True, key='plot_mesh')

    use_combos_plot = st.checkbox(
        "Use Combinations", value=bool(combos),
        disabled=not combos, key='plot_use_combo',
    )

    if use_combos_plot and combos:
        combo_names = [c['name'] for c in combos]
        selected_sources = st.multiselect(
            "Select Combinations", combo_names,
            default=combo_names[:3], key='plot_sources',
        )
    else:
        selected_sources = st.multiselect(
            "Select Load Cases", load_cases,
            default=load_cases[:3], key='plot_lc_sources',
        )

    # Detect available columns from first source
    avail_cols = sorted(set(PLOTTABLE_COLUMNS))
    selected_cols = st.multiselect(
        "Select Columns to Plot", avail_cols,
        default=[c for c in avail_cols if c in (
            'Fxx (kN/m)', 'Mxx (kN\u00b7m/m)',
            'Sig-xx_Top (kPa)', 'Sig-xx_Bottom (kPa)',
        )],
        key='plot_cols',
    )

    if st.button("🚀 Generate Plots", type="primary", key="btn_plot"):
        if not selected_sources or not selected_cols:
            st.warning("Please select at least one source and one column.")
        else:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            out_root = os.path.join(OUTPUT_FOLDER, f"plot_{timestamp}")
            total = len(selected_sources) * len(selected_cols)
            progress = st.progress(0, "Generating plots...")
            count = 0

            need_save = output_mode in ("Save Only", "Display & Save")
            save_tasks = []  # collect for multiprocessing

            for src in selected_sources:
                st.subheader(src)
                is_combo = use_combos_plot and bool(combos)
                arrays = _get_arrays_for_source(src, is_combo)
                _add_stress_arrays(arrays, thickness)

                # Prepare mesh data for the worker tuple
                if method == 'element-center':
                    x_w, y_w, tris_w = None, None, None
                    polys_w, cents_w = mesh.polygons, mesh.centroids
                else:
                    x_w, y_w, tris_w = mesh.x, mesh.y, mesh.triangles
                    polys_w, cents_w = None, None

                src_folder = safe_filename(src)
                load_folder = os.path.join(
                    out_root, f"Method_{safe_filename(method)}", src_folder,
                )
                if need_save:
                    os.makedirs(load_folder, exist_ok=True)

                plot_cols_ui = st.columns(2)
                for i, col_name in enumerate(selected_cols):
                    z = arrays.get(col_name)
                    if z is None:
                        count += 1
                        continue

                    with plot_cols_ui[i % 2]:
                        if output_mode in ("Display Only", "Display & Save"):
                            fig = generate_contour_plotly(
                                mesh, z, col_name, method,
                            )
                            st.plotly_chart(fig, use_container_width=True)

                        if need_save:
                            axial_arr = moment_arr = None
                            if col_name in STRESS_PAIRS:
                                f_col, m_col = STRESS_PAIRS[col_name]
                                axial_arr = arrays.get(f_col)
                                moment_arr = arrays.get(m_col)

                            suf = ("(Top Fiber)" if "Top" in col_name
                                   else "(Bottom Fiber)" if "Bottom" in col_name
                                   else "")
                            load_label = f"Comb: {src}" if is_combo else src

                            save_tasks.append((
                                x_w, y_w, z, tris_w, polys_w, cents_w,
                                col_name, col_name, suf, load_label,
                                load_folder, method, show_mesh,
                                axial_arr, moment_arr, theme,
                            ))

                    count += 1
                    progress.progress(count / total)

            # --- Process saves safely in main thread ---
            if need_save and save_tasks:
                st.info(f"Saving {len(save_tasks)} plots safely...")
                ok_count = 0
                err_count = 0
                
                # Sequential saving prevents Streamlit Tornado from starving and crashing
                for i, task in enumerate(save_tasks):
                    result = generate_plot_worker(task)
                    if result['status'] == 'ok':
                        ok_count += 1
                    else:
                        err_count += 1
                    
                    # Update progress visually to keep UI alive
                    progress.progress((i + 1) / len(save_tasks), f"Saving plot {i + 1} of {len(save_tasks)}...")
                            
                st.success(f"✅ Saved {ok_count} plots to `{out_root}`")
                if err_count:
                    st.warning(f"⚠ {err_count} plots failed.")

            progress.progress(1.0, "Done!")


# ─────────────── TAB 2: Report ───────────────
with tab_report:
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        report_format = st.selectbox(
            "Output Format", ['md', 'typst'], key='report_fmt',
        )
    with col_r2:
        master_toggle = st.checkbox(
            "Generate Master Summary", value=True, key='report_master',
        )

    use_combos_report = st.checkbox(
        "Use Combinations", value=bool(combos),
        disabled=not combos, key='report_use_combo',
    )

    if use_combos_report and combos:
        comb_filter = st.text_input(
            "Combination Filter (wildcard)", value="*", key='report_filter',
        )
        import fnmatch
        filtered_combos = [
            c for c in combos
            if fnmatch.fnmatch(c['name'], comb_filter)
        ]
        st.caption(f"Matched: {len(filtered_combos)} / {len(combos)}")
        report_sources = [(c['name'], True) for c in filtered_combos]
    else:
        report_sources = [(lc, False) for lc in load_cases]

    if st.button("📋 Generate Reports", type="primary", key="btn_report"):
        if not report_sources:
            st.warning("No sources to generate reports for.")
        else:
            ext = '.typ' if report_format == 'typst' else '.md'
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            out_root = os.path.join(OUTPUT_FOLDER, f"report_{timestamp}")
            all_stats = {}
            progress = st.progress(0, "Generating reports...")

            for idx, (src_name, is_combo) in enumerate(report_sources):
                arrays = _get_arrays_for_source(src_name, is_combo)
                if not arrays:
                    continue

                stats, n_pts = extract_statistics(arrays, mesh, thickness)
                label = f"Comb: {src_name}" if is_combo else src_name
                all_stats[label] = (stats, n_pts)

                title = f"Combination: {src_name}" if is_combo else f"Load Case: {src_name}"
                if report_format == 'typst':
                    content = render_report_typst(
                        title, stats, n_pts, thickness, method,
                    )
                else:
                    content = render_report_md(
                        title, stats, n_pts, thickness, method,
                    )

                folder = safe_filename(src_name)
                fpath = os.path.join(out_root, folder, f"Summary_{folder}{ext}")
                os.makedirs(os.path.dirname(fpath), exist_ok=True)
                with open(fpath, 'w', encoding='utf-8') as f:
                    f.write(content)

                progress.progress((idx + 1) / len(report_sources))

            # Master Summary
            master_content = None
            if master_toggle and all_stats:
                envelope = compute_master_envelope(all_stats)
                if report_format == 'typst':
                    master_content = render_master_typst(
                        envelope, thickness, method,
                    )
                else:
                    master_content = render_master_md(
                        envelope, thickness, method,
                    )

                master_path = os.path.join(out_root, f"MASTER_SUMMARY{ext}")
                with open(master_path, 'w', encoding='utf-8') as f:
                    f.write(master_content)

            progress.progress(1.0, "Done!")
            st.success(f"Generated {len(all_stats)} reports to `{out_root}`")

            # Preview master summary
            if master_content:
                st.divider()
                st.subheader("Master Summary Preview")
                if report_format == 'md':
                    st.markdown(master_content)
                else:
                    st.code(master_content, language='typst')

                st.download_button(
                    f"Download MASTER_SUMMARY{ext}",
                    master_content, f"MASTER_SUMMARY{ext}",
                    key='dl_master',
                )


# ─────────────── TAB 3: Rebar Analysis ───────────────
with tab_rebar:
    st.subheader("Material & Geometry")
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        fc = st.number_input("f'c (MPa)", value=DEFAULT_FC, step=5, key='rb_fc')
    with col_m2:
        fy = st.number_input("fy (MPa)", value=DEFAULT_FY, step=10, key='rb_fy')
    with col_m3:
        cover = st.number_input("Cover (mm)", value=DEFAULT_COVER, step=5, key='rb_cover')

    use_combos_rebar = st.checkbox(
        "Use Combinations", value=bool(combos),
        disabled=not combos, key='rb_use_combo',
    )

    if use_combos_rebar and combos:
        combo_names = [c['name'] for c in combos]
        rb_sources = st.multiselect(
            "Select Combinations", combo_names,
            default=combo_names[:2], key='rb_sources',
        )
        rb_is_combo = True
    else:
        rb_sources = st.multiselect(
            "Select Load Cases", load_cases,
            default=load_cases[:2], key='rb_lc_sources',
        )
        rb_is_combo = False

    rb_output = st.radio(
        "Output", ["Envelope Only", "Per Source", "Both"],
        key='rb_output', horizontal=True,
    )
    rb_save = st.checkbox("Save plots to output/", value=False, key='rb_save')

    # ── Sub-tabs: Lentur vs Geser ──
    sub_flexure, sub_shear = st.tabs(["💪 Lentur (Flexure)", "✂️ Geser (Shear)"])

    # ════════════════════════════════════════════════════
    # SUB-TAB: FLEXURE (existing logic, unchanged)
    # ════════════════════════════════════════════════════
    with sub_flexure:
        rebar_mode = st.radio(
            "Analysis Mode",
            ["Input Spacing -> Output Diameter", "Input Diameter -> Output Spacing"],
            key='rb_mode',
        )

        if "Spacing" in rebar_mode.split("->")[0]:
            spacing_input = st.number_input(
                "Spacing (mm)", value=150, step=25, key='rb_spacing',
            )
            diameter_input = None
        else:
            diameter_input = st.selectbox(
                "Diameter (mm)",
                [int(d) for d in AVAILABLE_DIAMETERS],
                index=1, key='rb_diameter',
            )
            spacing_input = None

        REBAR_CASES = [
            ('Mxx (kN\u00b7m/m)', 'x', 'bottom', 'Mxx_Bottom_X'),
            ('Mxx (kN\u00b7m/m)', 'x', 'top',    'Mxx_Top_X'),
            ('Myy (kN\u00b7m/m)', 'y', 'bottom', 'Myy_Bottom_Y'),
            ('Myy (kN\u00b7m/m)', 'y', 'top',    'Myy_Top_Y'),
        ]

        if st.button("🧮 Analyze Flexural Rebar", type="primary", key="btn_rebar"):
            if not rb_sources:
                st.warning("Please select at least one source.")
            else:
                h_mm = thickness * 1000
                D_ref = float(diameter_input or AVAILABLE_DIAMETERS[1])
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                out_root = os.path.join(OUTPUT_FOLDER, f"rebar_{timestamp}")

                show_envelope = rb_output in ("Envelope Only", "Both")
                show_per_src = rb_output in ("Per Source", "Both")

                if method == 'element-center':
                    x_w, y_w, tris_w = None, None, None
                    polys_w, cents_w = mesh.polygons, mesh.centroids
                else:
                    x_w, y_w, tris_w = mesh.x, mesh.y, mesh.triangles
                    polys_w, cents_w = None, None

                show_mesh_rb = False
                theme_rb = 'light'
                rebar_save_tasks = []

                # ── Compute per-source results ──
                all_results = {}
                for src in rb_sources:
                    arrays = _get_arrays_for_source(src, rb_is_combo)
                    src_results = {}

                    for moment_col, direction, layer, label in REBAR_CASES:
                        m_arr = arrays.get(moment_col)
                        if m_arr is None:
                            continue

                        if layer == 'bottom':
                            Mu = np.where(m_arr > 0, m_arr, 0)
                        else:
                            Mu = np.where(m_arr < 0, np.abs(m_arr), 0)

                        d_eff = calc_effective_depth(h_mm, cover, D_ref, direction, layer)
                        As = calc_as_required(Mu, fc, fy, d_eff)

                        if diameter_input is not None:
                            result = calc_spacing_from_diameter(As, float(diameter_input))
                            plot_mode = 'spacing'
                        else:
                            result = calc_diameter_from_spacing(As, float(spacing_input))
                            plot_mode = 'diameter'

                        src_results[label] = result

                    all_results[src] = src_results

                if diameter_input is not None:
                    mode_prefix = f"Spacing D{diameter_input}"
                    plot_mode = 'spacing'
                    unit_label = 'mm'
                else:
                    mode_prefix = f"Diameter s{spacing_input}"
                    plot_mode = 'diameter'
                    unit_label = 'mm'

                subtitle = f"h={h_mm:.0f}mm | fc={fc} | fy={fy} | cover={cover}mm"

                # ── Envelope ──
                if show_envelope:
                    st.subheader("📐 Envelope (All Selected Sources)")
                    env_cols = st.columns(2)
                    for case_idx, (_, _, _, label) in enumerate(REBAR_CASES):
                        case_arrays = [
                            all_results[src][label]
                            for src in rb_sources
                            if label in all_results.get(src, {})
                        ]
                        if not case_arrays:
                            continue

                        stacked = np.stack(case_arrays)
                        if plot_mode == 'diameter':
                            envelope = np.nanmax(stacked, axis=0)
                        else:
                            envelope = np.nanmin(stacked, axis=0)

                        env_label = f"ENVELOPE {mode_prefix} - {label}"
                        with env_cols[case_idx % 2]:
                            fig = generate_rebar_plotly(
                                mesh, envelope, env_label, method, mode=plot_mode,
                            )
                            st.plotly_chart(fig, use_container_width=True)

                            if rb_save:
                                env_folder = os.path.join(out_root, "Envelope_Rebar")
                                os.makedirs(env_folder, exist_ok=True)
                                rebar_save_tasks.append((
                                    x_w, y_w, envelope, tris_w, polys_w, cents_w,
                                    env_label, unit_label, subtitle,
                                    "Envelope", env_folder, method,
                                    show_mesh_rb, theme_rb,
                                    f"ENVELOPE_{safe_filename(env_label)}",
                                ))

                # ── Per Source ──
                if show_per_src:
                    for src in rb_sources:
                        st.subheader(src)
                        plot_cols_ui = st.columns(2)

                        for case_idx, (_, _, _, label) in enumerate(REBAR_CASES):
                            result = all_results.get(src, {}).get(label)
                            if result is None:
                                continue

                            result_label = f"{mode_prefix} - {label}"
                            with plot_cols_ui[case_idx % 2]:
                                fig = generate_rebar_plotly(
                                    mesh, result, result_label, method, mode=plot_mode,
                                )
                                st.plotly_chart(fig, use_container_width=True)

                                if rb_save:
                                    src_folder = os.path.join(
                                        out_root, safe_filename(src),
                                    )
                                    os.makedirs(src_folder, exist_ok=True)
                                    rebar_save_tasks.append((
                                        x_w, y_w, result, tris_w, polys_w, cents_w,
                                        result_label, unit_label, subtitle,
                                        src, src_folder, method,
                                        show_mesh_rb, theme_rb,
                                        safe_filename(result_label),
                                    ))

                # --- Process saves safely in main thread ---
                if rb_save and rebar_save_tasks:
                    st.info(f"Saving {len(rebar_save_tasks)} rebar plots safely...")
                    ok_count = 0
                    err_count = 0

                    rb_prog = st.progress(0, "Saving rebar plots...")
                    for i, task in enumerate(rebar_save_tasks):
                        result = generate_rebar_plot_worker(task)
                        if result['status'] == 'ok':
                            ok_count += 1
                        else:
                            err_count += 1

                        rb_prog.progress((i + 1) / len(rebar_save_tasks), f"Saving plot {i + 1} of {len(rebar_save_tasks)}...")

                    st.success(f"✅ Saved {ok_count} rebar plots to `{out_root}`")
                    if err_count:
                        st.warning(f"⚠ {err_count} plots failed.")

                st.success("✅ Flexural rebar analysis complete!")

    # ════════════════════════════════════════════════════
    # SUB-TAB: SHEAR (new feature)
    # ════════════════════════════════════════════════════
    with sub_shear:
        st.caption("Analisis tulangan geser berdasarkan Vxx dan Vyy (ACI 318 / SNI 2847)")

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            shear_s_long = st.number_input(
                "Spasi Longitudinal (mm)", value=150, step=25, key='sh_s_long',
                help="Jarak antar sengkang searah gaya geser",
            )
        with col_s2:
            shear_s_trans = st.number_input(
                "Spasi Transversal (mm)", value=150, step=25, key='sh_s_trans',
                help="Jarak antar kaki sengkang melintang (pembagi lebar 1m)",
            )

        SHEAR_CASES_UI = [
            ('Vxx (kN/m)', 'x', 'Vxx_Shear_X'),
            ('Vyy (kN/m)', 'y', 'Vyy_Shear_Y'),
        ]

        if st.button("✂️ Analyze Shear Rebar", type="primary", key="btn_shear"):
            if not rb_sources:
                st.warning("Please select at least one source.")
            else:
                h_mm = thickness * 1000
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                out_root = os.path.join(OUTPUT_FOLDER, f"shear_{timestamp}")

                show_envelope = rb_output in ("Envelope Only", "Both")
                show_per_src = rb_output in ("Per Source", "Both")

                if method == 'element-center':
                    x_w, y_w, tris_w = None, None, None
                    polys_w, cents_w = mesh.polygons, mesh.centroids
                else:
                    x_w, y_w, tris_w = mesh.x, mesh.y, mesh.triangles
                    polys_w, cents_w = None, None

                show_mesh_sh = False
                theme_sh = 'light'
                shear_save_tasks = []

                # ── Compute per-source shear results ──
                all_shear_results = {}  # {src: {label: {'avs': arr, 'diameter': arr}}}
                for src in rb_sources:
                    arrays = _get_arrays_for_source(src, rb_is_combo)
                    src_results = {}

                    for shear_col, direction, label in SHEAR_CASES_UI:
                        v_arr = arrays.get(shear_col)
                        if v_arr is None:
                            continue

                        D_for_depth = 16.0
                        dv = calc_effective_depth(h_mm, cover, D_for_depth, direction, 'bottom')
                        Av_s = calc_shear_Av_per_s(v_arr, fc, fy, dv)

                        # Spacing convention
                        if direction == 'x':
                            s_l, s_t = shear_s_long, shear_s_trans
                        else:
                            s_l, s_t = shear_s_trans, shear_s_long

                        D_shear = calc_shear_diameter(Av_s, s_l, s_t)

                        src_results[label] = {
                            'avs': Av_s,
                            'diameter': D_shear,
                            'dv': dv,
                            's_l': s_l,
                            's_t': s_t,
                        }

                    all_shear_results[src] = src_results

                subtitle_sh = f"h={h_mm:.0f}mm | fc={fc} | fy={fy} | cover={cover}mm"

                # ── Envelope ──
                if show_envelope:
                    st.subheader("📐 Shear Envelope (All Selected Sources)")
                    env_cols = st.columns(2)

                    for case_idx, (_, direction, label) in enumerate(SHEAR_CASES_UI):
                        # Av/s envelope
                        avs_arrays = [
                            all_shear_results[src][label]['avs']
                            for src in rb_sources
                            if label in all_shear_results.get(src, {})
                        ]
                        if not avs_arrays:
                            continue

                        avs_env = np.fmax.reduce(avs_arrays)
                        dir_label = "Arah X" if direction == 'x' else "Arah Y"

                        with env_cols[case_idx % 2]:
                            # Av/s plot
                            avs_label = f"ENVELOPE Av/s — {dir_label}"
                            fig = generate_rebar_plotly(
                                mesh, avs_env, avs_label, method, mode='spacing',
                            )
                            st.plotly_chart(fig, use_container_width=True)

                            # Diameter plot
                            if direction == 'x':
                                s_l, s_t = shear_s_long, shear_s_trans
                            else:
                                s_l, s_t = shear_s_trans, shear_s_long

                            D_env = calc_shear_diameter(avs_env, s_l, s_t)
                            d_label = f"ENVELOPE Diameter s={int(s_l)}×{int(s_t)}mm — {dir_label}"
                            fig2 = generate_rebar_plotly(
                                mesh, D_env, d_label, method, mode='diameter',
                            )
                            st.plotly_chart(fig2, use_container_width=True)

                            if rb_save:
                                env_folder = os.path.join(out_root, "Envelope_Shear")
                                os.makedirs(env_folder, exist_ok=True)
                                shear_save_tasks.append((
                                    x_w, y_w, avs_env, tris_w, polys_w, cents_w,
                                    avs_label, 'mm²/mm', subtitle_sh,
                                    "Envelope", env_folder, method,
                                    show_mesh_sh, theme_sh,
                                    f"ENVELOPE_{safe_filename(avs_label)}",
                                ))
                                shear_save_tasks.append((
                                    x_w, y_w, D_env, tris_w, polys_w, cents_w,
                                    d_label, 'mm', subtitle_sh,
                                    "Envelope", env_folder, method,
                                    show_mesh_sh, theme_sh,
                                    f"ENVELOPE_{safe_filename(d_label)}",
                                ))

                # ── Per Source ──
                if show_per_src:
                    for src in rb_sources:
                        st.subheader(f"✂️ {src}")
                        plot_cols_ui = st.columns(2)

                        for case_idx, (_, direction, label) in enumerate(SHEAR_CASES_UI):
                            res = all_shear_results.get(src, {}).get(label)
                            if res is None:
                                continue

                            dir_label = "Arah X" if direction == 'x' else "Arah Y"

                            with plot_cols_ui[case_idx % 2]:
                                # Av/s plot
                                avs_label = f"Av/s Geser — {dir_label}"
                                fig = generate_rebar_plotly(
                                    mesh, res['avs'], avs_label, method, mode='spacing',
                                )
                                st.plotly_chart(fig, use_container_width=True)

                                # Diameter plot
                                s_l, s_t = res['s_l'], res['s_t']
                                d_label = f"Diameter Sengkang s={int(s_l)}×{int(s_t)}mm — {dir_label}"
                                fig2 = generate_rebar_plotly(
                                    mesh, res['diameter'], d_label, method, mode='diameter',
                                )
                                st.plotly_chart(fig2, use_container_width=True)

                                if rb_save:
                                    src_folder = os.path.join(out_root, safe_filename(src))
                                    os.makedirs(src_folder, exist_ok=True)
                                    shear_save_tasks.append((
                                        x_w, y_w, res['avs'], tris_w, polys_w, cents_w,
                                        avs_label, 'mm²/mm', subtitle_sh,
                                        src, src_folder, method,
                                        show_mesh_sh, theme_sh,
                                        safe_filename(avs_label),
                                    ))
                                    shear_save_tasks.append((
                                        x_w, y_w, res['diameter'], tris_w, polys_w, cents_w,
                                        d_label, 'mm', subtitle_sh,
                                        src, src_folder, method,
                                        show_mesh_sh, theme_sh,
                                        safe_filename(d_label),
                                    ))

                # --- Process saves safely in main thread ---
                if rb_save and shear_save_tasks:
                    st.info(f"Saving {len(shear_save_tasks)} shear plots safely...")
                    ok_count = 0
                    err_count = 0

                    sh_prog = st.progress(0, "Saving shear plots...")
                    for i, task in enumerate(shear_save_tasks):
                        result = generate_rebar_plot_worker(task)
                        if result['status'] == 'ok':
                            ok_count += 1
                        else:
                            err_count += 1

                        sh_prog.progress((i + 1) / len(shear_save_tasks), f"Saving plot {i + 1} of {len(shear_save_tasks)}...")

                    st.success(f"✅ Saved {ok_count} shear plots to `{out_root}`")
                    if err_count:
                        st.warning(f"⚠ {err_count} plots failed.")

                st.success("✅ Shear rebar analysis complete!")
