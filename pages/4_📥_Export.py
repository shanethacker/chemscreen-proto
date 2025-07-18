"""
Export page for ChemScreen multipage application.
"""

import logging
import sys
import time
from pathlib import Path
from typing import Any, Optional

import streamlit as st

# Add the project root to the path
sys.path.append(str(Path(__file__).parent.parent))

# Import ChemScreen modules
from chemscreen.analyzer import calculate_quality_metrics
from chemscreen.config import initialize_config
from chemscreen.errors import (
    log_error_for_support,
    show_error_with_help,
)
from chemscreen.exporter import ExportManager
from chemscreen.models import BatchSearchSession, SearchParameters
from shared.app_utils import init_session_state

# Import shared utilities
from shared.ui_utils import (
    create_progress_with_cancel,
    load_custom_css,
    setup_sidebar,
    show_success_with_stats,
)

# Initialize configuration and logging
config = initialize_config()
logging.basicConfig(
    level=getattr(logging, config.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="Export - ChemScreen",
    page_icon="📥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session state and UI
init_session_state()
load_custom_css()

setup_sidebar()


def show_export_page() -> None:
    """Display the export page."""
    st.title("📥 Export Results")

    if not st.session_state.search_results:
        st.warning("⚠️ No results to export. Please run a search first.")
        st.page_link("pages/2_🔍_Search.py", label="Go to Search", icon="▶️")
        return

    st.markdown("Export your search results in various formats for further analysis.")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Export Options")

        export_format = st.radio(
            "Select Export Format",
            options=["CSV", "Excel (XLSX)", "JSON"],
            help="Choose the format for your export file",
        )

        include_metadata = st.checkbox(
            "Include Search Metadata",
            value=True,
            help="Include search parameters and timestamp",
        )

        include_abstracts = st.checkbox(
            "Include Abstracts",
            value=False,
            help="Include paper abstracts (increases file size)",
        )

        if export_format == "Excel (XLSX)":
            st.info(
                "Excel export will create multiple sheets: Summary, Detailed Results, and Metadata"
            )

    with col2:
        st.subheader("Export Preview")

        # Show export summary
        if st.session_state.search_results:
            total_publications = sum(
                len(result.publications) for result in st.session_state.search_results
            )
            successful_searches = len(
                [r for r in st.session_state.search_results if not r.error]
            )

            st.write("**Export will include:**")
            st.write(f"• {len(st.session_state.chemicals)} chemicals")
            st.write(f"• {successful_searches} successful searches")
            st.write(f"• {total_publications} publications")
            if include_abstracts:
                st.write("• Publication abstracts")
            if include_metadata:
                st.write("• Search metadata and parameters")
        else:
            st.info("No data available for export preview")

    st.markdown("---")

    # Export button with real export functionality
    if st.button("📥 Generate Export", type="primary"):
        # Create progress indicators for export
        progress_bar: Any
        status_text: Any
        cancel_button: Any
        progress_container: Any
        progress_bar, status_text, cancel_button, progress_container = (
            create_progress_with_cancel("Generating export")
        )

        try:
            # Initialize export manager
            export_manager = ExportManager()

            # Prepare data for export
            status_text.text("📊 Collecting search results...")
            progress_bar.progress(0.2)

            if bool(cancel_button):
                st.warning("⏸️ Export cancelled by user")
                progress_container.empty()
                return

            # Create session object for export
            search_results = st.session_state.search_results
            batch_id = st.session_state.get("current_batch_id", "unknown")

            # Create search parameters from session state
            search_params = SearchParameters(
                date_range_years=st.session_state.settings["date_range_years"],
                max_results=st.session_state.settings["max_results_per_chemical"],
                include_reviews=st.session_state.settings["include_reviews"],
                use_cache=st.session_state.settings["cache_enabled"],
            )

            # Create session object
            session = BatchSearchSession(
                batch_id=batch_id,
                chemicals=st.session_state.chemicals,
                parameters=search_params,
                status="completed",
            )

            # Prepare results with quality metrics
            status_text.text("📋 Calculating quality metrics...")
            progress_bar.progress(0.4)

            results_with_metrics = []
            for result in search_results:
                metrics = calculate_quality_metrics(result)
                results_with_metrics.append((result, metrics))

            # Generate export based on format
            status_text.text("📄 Creating export file...")
            progress_bar.progress(0.7)

            filepath: Optional[Path] = None
            mime_type = "text/csv"

            if export_format == "CSV":
                filepath = export_manager.export_to_csv(
                    results=results_with_metrics,
                    session=session,
                    include_abstracts=include_abstracts,
                )
                mime_type = "text/csv"
            elif export_format == "Excel (XLSX)":
                filepath = export_manager.export_to_excel(
                    results=results_with_metrics,
                    session=session,
                    include_abstracts=include_abstracts,
                )
                mime_type = (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            elif export_format == "JSON":
                filepath = export_manager.export_to_json(
                    results=results_with_metrics, session=session
                )
                mime_type = "application/json"
            else:
                # Default to CSV if format is unexpected
                filepath = export_manager.export_to_csv(
                    results=results_with_metrics,
                    session=session,
                    include_abstracts=include_abstracts,
                )
                mime_type = "text/csv"

            if filepath is None:
                st.error("❌ Failed to generate export file")
                return

            status_text.text("✅ Export ready!")
            progress_bar.progress(1.0)
            time.sleep(0.3)
            progress_container.empty()

            # Read the generated file for download
            with open(filepath, "rb") as f:
                file_data = f.read()

            # Show success with real file info
            file_size_kb = len(file_data) / 1024
            stats = {
                "File Size": f"{file_size_kb:.1f} KB",
                "Chemicals": len(st.session_state.chemicals),
                "Format": export_format,
                "Publications": sum(
                    len(result.publications) for result, _ in results_with_metrics
                ),
            }
            show_success_with_stats(
                "Export file generated successfully!", stats, show_balloons=False
            )

            # Provide actual download button
            st.download_button(
                label="📥 Download Export",
                data=file_data,
                file_name=filepath.name,
                mime=mime_type,
            )

            # Quick actions after export
            st.markdown("---")
            st.subheader("Next Steps")

            col1, col2 = st.columns(2)

            with col1:
                if st.button("📊 View Results Again", use_container_width=True):
                    st.switch_page("pages/3_📊_Results.py")

            with col2:
                if st.button("🔍 New Search", use_container_width=True):
                    st.switch_page("pages/2_🔍_Search.py")

        except Exception as e:
            progress_container.empty()

            # Determine specific export error type
            error_message = str(e).lower()
            if "permission" in error_message or "access" in error_message:
                show_error_with_help(
                    "file_permission_error",
                    f"Cannot write export file: {str(e)}",
                    expand_help=True,
                )
            elif "disk" in error_message or "space" in error_message:
                show_error_with_help(
                    "disk_space_error", f"Insufficient disk space: {str(e)}"
                )
            elif "memory" in error_message or "too large" in error_message:
                show_error_with_help(
                    "large_dataset_error", f"Dataset too large for export: {str(e)}"
                )
            elif export_format == "Excel (XLSX)" and "openpyxl" in error_message:
                show_error_with_help("excel_error", f"Excel export failed: {str(e)}")
            else:
                show_error_with_help(
                    "export_failed", f"Export generation failed: {str(e)}"
                )

            log_error_for_support(e, "export generation")


# Main execution
if __name__ == "__main__":
    show_export_page()
else:
    show_export_page()
