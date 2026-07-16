"""
Textual TUI for the Thermo Raw File Converter.
All settings are presented on a single scrollable page.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RadioButton,
    RadioSet,
    RichLog,
    Rule,
    Static,
)

from .main import (
    MSCONVERT_VERSIONS,
    SCRIPT_DIR,
    THERMOCONVERT_VERSIONS,
    collect_raw_files,
    get_tool_paths,
    get_version,
    install_tool,
    run_conversion,
)
from .filterMZML import MzmlFilter

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

CSS = """
Screen {
    background: $surface;
}

#scroll {
    height: 1fr;
    border: solid $primary;
    padding: 0 1;
}

.section-title {
    text-style: bold;
    color: green;
    border-bottom: solid green;
    padding: 1 0 0 0;
    margin-bottom: 1;
}

.hint {
    color: $text-muted;
    padding: 0 0 0 2;
}

RadioSet {
    padding: 0 0 0 2;
}

RadioButton {
    color: orange;
}

RadioButton:focus {
    background: darkorange 30%;
}

RadioButton.-on .toggle--button {
    color: orange;
    background: darkorange 40%;
}

Checkbox {
    padding: 0 0 0 2;
    color: orange;
}

Checkbox:focus {
    background: darkorange 30%;
}

Checkbox.-on .toggle--button {
    color: orange;
    background: darkorange 40%;
}

Input {
    margin: 0 0 0 2;
    width: 60;
    border: tall darkorange 60%;
}

Input:focus {
    border: tall orange;
}

#btn-row {
    height: auto;
    padding: 1 0;
    align: center middle;
}

#btn-start {
    min-width: 20;
}

#btn-download-thermo {
    min-width: 30;
    background: darkorange;
    color: $text;
}

#btn-download-msconvert {
    min-width: 30;
    background: darkorange;
    color: $text;
}

#btn-scan {
    background: darkorange;
    color: $text;
}

#log {
    height: 20;
    border: solid $primary;
    margin: 1 0;
}

.tool-status {
    padding: 0 0 0 2;
    color: $success;
}

.tool-status-missing {
    padding: 0 0 0 2;
    color: $error;
}

/* Two-column converter layout */
#converter-columns {
    height: auto;
}

#converter-left {
    width: 30%;
    height: auto;
}

#converter-right {
    width: 70%;
    height: auto;
    padding: 0 0 0 2;
}

/* Source folder row: input + button side by side */
#source-row {
    height: auto;
    align: left middle;
}

#source-row Input {
    width: 1fr;
    margin: 0;
}

#btn-scan {
    margin: 0 0 0 1;
    min-width: 16;
}

#scan-result {
    padding: 0 0 0 2;
    color: $text-muted;
}

/* Small inline logs under buttons */
.inline-log {
    height: 4;
    border: solid $primary-darken-2;
    margin: 0 0 0 2;
    padding: 0;
    background: $surface-darken-1;
}

#progress-bar {
    margin: 0 0 0 2;
    width: 60;
}

#progress-label {
    padding: 0 0 0 2;
    color: $text-muted;
}

#panel-thermo-ver {
    height: auto;
    padding: 0;
}

#panel-msconvert-ver {
    height: auto;
    padding: 0;
}

/* Collision-energy min/max side-by-side */
#ce-row {
    height: auto;
    align: left middle;
}

#ce-row Label {
    width: auto;
    padding: 0 1 0 2;
}

#ce-row Input {
    width: 14;
}

/* Exact CE values */
#ce-exact-row {
    height: auto;
    align: left middle;
}

#ce-exact-row Label {
    width: auto;
    padding: 0 1 0 2;
}

#ce-exact-row Input {
    width: 40;
}

/* Filter-string preset buttons */
#filter-preset-row {
    height: auto;
    align: left middle;
    padding: 0 0 0 2;
}

.filter-preset-btn {
    min-width: 12;
    margin: 0 1 0 0;
    background: $surface-lighten-1;
    color: $text;
}
"""


class Convert2RawApp(App):
    """Single-page TUI for the RAW → mzML conversion pipeline."""

    TITLE = f"Thermo Raw File Converter  v{get_version()}"
    CSS = CSS
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [Binding("ctrl+q", "quit", "Close")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

        with ScrollableContainer(id="scroll"):
            # ----------------------------------------------------------------
            # File selection  (moved above folders)
            # ----------------------------------------------------------------
            yield Static("🔎  File Selection", classes="section-title")
            with RadioSet(id="rs-recursive"):
                yield RadioButton("Include subfolders (mirror structure)", value=True, id="rb-recursive-yes")
                yield RadioButton("Top-level files only", id="rb-recursive-no")
            yield Static("If output folder already exists:", classes="hint")
            with RadioSet(id="rs-existing"):
                yield RadioButton("Skip already-converted files  [default]", value=True, id="rb-skip")
                yield RadioButton("Reprocess all (delete existing output)", id="rb-reprocess")
            yield Rule()

            # ----------------------------------------------------------------
            # Folders
            # ----------------------------------------------------------------
            yield Static("📁  Folders", classes="section-title")
            yield Label("Source folder (contains .raw files):")
            with Horizontal(id="source-row"):
                yield Input(placeholder="e.g. C:\\data\\raw", id="inp-source", value="..\\")
                yield Button("🔍 Scan", id="btn-scan", variant="default")
            yield RichLog(id="scan-log", highlight=True, markup=True, wrap=True, classes="inline-log")
            yield Label("Output folder (mzML files will be written here):")
            yield Input(placeholder="e.g. C:\\data\\mzMLs", id="inp-output", value="..\\mzMLs")
            yield Rule()

            # ----------------------------------------------------------------
            # Converter — two-column layout
            # ----------------------------------------------------------------
            yield Static("⚙️  Converter", classes="section-title")
            with Horizontal(id="converter-columns"):
                # Left column: software selection
                with Vertical(id="converter-left"):
                    yield Static("Software:", classes="hint")
                    with RadioSet(id="rs-converter"):
                        yield RadioButton("ThermoRawFileParser  [default]", value=True, id="rb-thermo")
                        yield RadioButton("MSConvert", id="rb-msconvert")

                # Right column: version panels (only one visible at a time)
                with Vertical(id="converter-right"):
                    # --- Thermo version panel ---
                    with Vertical(id="panel-thermo-ver"):
                        yield Static("ThermoRawFileParser version:", classes="hint")
                        with RadioSet(id="rs-thermo-ver"):
                            for i, v in enumerate(THERMOCONVERT_VERSIONS):
                                yield RadioButton(v["label"], value=(i == 1), id=f"rb-thermo-ver-{i}")
                        yield Static(self._tool_status_text("thermo", 2), id="thermo-status", classes="tool-status")
                        yield Button("Download / Install ThermoRawFileParser", id="btn-download-thermo", variant="default")
                        yield RichLog(id="thermo-log", highlight=True, markup=True, wrap=True, classes="inline-log")

                    # --- MSConvert version panel (hidden initially) ---
                    with Vertical(id="panel-msconvert-ver"):
                        yield Static("MSConvert version:", classes="hint")
                        with RadioSet(id="rs-msconvert-ver"):
                            for i, v in enumerate(MSCONVERT_VERSIONS):
                                yield RadioButton(v["label"], value=(i == 0), id=f"rb-msconvert-ver-{i}")
                        yield Static(self._tool_status_text("msconvert", 0), id="msconvert-status", classes="tool-status")
                        yield Button("Download / Install MSConvert", id="btn-download-msconvert", variant="default")
                        yield RichLog(id="msconvert-log", highlight=True, markup=True, wrap=True, classes="inline-log")

            yield Rule()

            # ----------------------------------------------------------------
            # MSMS correction
            # ----------------------------------------------------------------
            yield Static("🔬  MSMS Precursor Correction", classes="section-title")
            yield Static(
                "Some Thermo instruments occasionally report an incorrect precursor m/z for MS\u00b2 spectra — "
                "this does not happen on every instrument or every run, but when it does it can "
                "cause incorrect peptide identification. "
                "The converter can detect and fix this automatically: it reads the actual isolation window centre "
                "(CV term MS:1000827) from the mzML and replaces the reported selected-ion m/z "
                "(MS:1000744) whenever the two values differ by more than the set tolerance.",
                classes="hint",
            )
            with RadioSet(id="rs-fix"):
                yield RadioButton("Fix incorrect MSMS precursor m/z  [default]", value=True, id="rb-fix-yes")
                yield RadioButton("Skip correction", id="rb-fix-no")
            yield Label("Output file suffix for corrected mzML (leave blank to overwrite in-place):")
            yield Input(placeholder="e.g.  _fixed   —  blank = overwrite original", id="inp-newext", value="")
            yield Rule()

            # ----------------------------------------------------------------
            # Timestamp suffix / prefix
            # ----------------------------------------------------------------
            yield Static("🕐  File Naming", classes="section-title")
            yield Static("Add acquisition timestamp (YYYY_MM_DD_HH_MM) to name:", classes="hint")
            with RadioSet(id="rs-timestamp"):
                yield RadioButton("No timestamp  [default]", value=True, id="rb-ts-no")
                yield RadioButton("As prefix:  [bold]YYYY_MM_DD_HH_MM__[/bold]filename.mzML", id="rb-ts-prefix")
                yield RadioButton("As suffix:  filename[bold]__YYYY_MM_DD_HH_MM[/bold].mzML", id="rb-ts-suffix")
            yield Rule()

            # ----------------------------------------------------------------
            # Spectrum filters (post-conversion mzML)
            # ----------------------------------------------------------------
            yield Static("🔍  Spectrum Filters  (post-conversion mzML)", classes="section-title")
            yield Static(
                "Applied after conversion. All active criteria are combined with AND logic. Spectra that do not satisfy all active criteria are removed from the output mzML.",
                classes="hint",
            )

            yield Static("MS levels to keep (unchecked = keep all):", classes="hint")
            yield Checkbox("Keep MS1 scans", id="cb-filter-ms1", value=False)
            yield Checkbox("Keep MS2 scans", id="cb-filter-ms2", value=False)

            yield Static("Collision energy filter (eV):", classes="hint")
            yield Static("  Range (blank = no limit):", classes="hint")
            with Horizontal(id="ce-row"):
                yield Label("Min:")
                yield Input(placeholder="e.g. 20", id="inp-ce-min", value="")
                yield Label("Max:")
                yield Input(placeholder="e.g. 60", id="inp-ce-max", value="")
            yield Static("  Exact values — semicolon-separated list (blank = no filter):", classes="hint")
            with Horizontal(id="ce-exact-row"):
                yield Label("Values:")
                yield Input(placeholder="e.g. 35;45;60", id="inp-ce-values", value="")

            yield Label("Filter string regex (blank = no filter):")
            yield Static("  Presets:", classes="hint")
            with Horizontal(id="filter-preset-row"):
                yield Button("FTMS.*", id="btn-preset-ftms", classes="filter-preset-btn")
                yield Button("ITMS.*", id="btn-preset-itms", classes="filter-preset-btn")
                yield Button("ms2.*", id="btn-preset-ms2", classes="filter-preset-btn")
                yield Button("Clear", id="btn-preset-clear", classes="filter-preset-btn")
            yield Input(
                placeholder=r"e.g.  FTMS.*",
                id="inp-filter-regex",
                value="",
            )
            yield Rule()

            # ----------------------------------------------------------------
            # Parallelism
            # ----------------------------------------------------------------
            yield Static("⚡  Parallelism", classes="section-title")
            yield Static(f"System CPU count: {os.cpu_count() or 1}", classes="hint")
            yield Label("Number of parallel conversion threads:")
            yield Input(placeholder="4", id="inp-threads", value="4")
            yield Rule()

            # ----------------------------------------------------------------
            # Start button + progress
            # ----------------------------------------------------------------
            with Horizontal(id="btn-row"):
                yield Button("▶  Start Conversion", id="btn-start", variant="primary")
            yield Static("", id="progress-label")
            yield ProgressBar(id="progress-bar", total=1, show_eta=False)

            # ----------------------------------------------------------------
            # Log
            # ----------------------------------------------------------------
            yield Static("📋  Log", classes="section-title")
            yield RichLog(id="log", highlight=True, markup=True, wrap=True)

    def on_mount(self) -> None:
        # Hide scan log and progress bar until needed
        self.query_one("#scan-log", RichLog).display = False
        self.query_one("#progress-bar", ProgressBar).display = False
        self.query_one("#progress-label", Static).display = False
        # Apply initial visibility: ThermoRawFileParser selected by default
        self._apply_converter_visibility(is_thermo=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _tool_status_text(self, tool: str, idx: int) -> str:
        versions = THERMOCONVERT_VERSIONS if tool == "thermo" else MSCONVERT_VERSIONS
        exe = SCRIPT_DIR / "sw" / versions[idx]["exe_rel"]
        if exe.exists():
            return f"✔ Installed: {exe}"
        return f"✘ Not installed: {exe}"

    def _selected_index(self, radioset_id: str) -> int:
        rs = self.query_one(f"#{radioset_id}", RadioSet)
        return rs.pressed_index or 0

    def _update_progress(self, completed: int, total: int) -> None:
        def _apply() -> None:
            bar = self.query_one("#progress-bar", ProgressBar)
            label = self.query_one("#progress-label", Static)
            bar.update(total=total, progress=completed)
            label.update(f"Converting: {completed} / {total} file(s) done")
            if completed >= total:
                label.update(f"[green]✔ Done — {completed} / {total} file(s) converted[/green]")

        self.call_from_thread(_apply)

    def _log(self, msg: str) -> None:
        log_widget = self.query_one("#log", RichLog)
        self.call_from_thread(log_widget.write, msg)

    def _apply_converter_visibility(self, is_thermo: bool) -> None:
        self.query_one("#panel-thermo-ver").display = is_thermo
        self.query_one("#panel-msconvert-ver").display = not is_thermo

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        rs_id = event.radio_set.id
        if rs_id == "rs-converter":
            is_thermo = (event.radio_set.pressed_index or 0) == 0
            self._apply_converter_visibility(is_thermo)
        elif rs_id == "rs-thermo-ver":
            idx = event.radio_set.pressed_index or 0
            self.query_one("#thermo-status", Static).update(self._tool_status_text("thermo", idx))
        elif rs_id == "rs-msconvert-ver":
            idx = event.radio_set.pressed_index or 0
            self.query_one("#msconvert-status", Static).update(self._tool_status_text("msconvert", idx))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-start":
            self._start_conversion()
        elif event.button.id == "btn-scan":
            self._scan_source_folder()
        elif event.button.id == "btn-download-thermo":
            self._download_tool("thermo")
        elif event.button.id == "btn-download-msconvert":
            self._download_tool("msconvert")
        elif event.button.id == "btn-preset-ftms":
            self.query_one("#inp-filter-regex", Input).value = "FTMS.*"
        elif event.button.id == "btn-preset-itms":
            self.query_one("#inp-filter-regex", Input).value = "ITMS.*"
        elif event.button.id == "btn-preset-ms2":
            self.query_one("#inp-filter-regex", Input).value = "ms2.*"
        elif event.button.id == "btn-preset-clear":
            self.query_one("#inp-filter-regex", Input).value = ""

    # ------------------------------------------------------------------
    # Folder scan
    # ------------------------------------------------------------------

    def _scan_log(self, msg: str) -> None:
        scan_log = self.query_one("#scan-log", RichLog)
        self.call_from_thread(scan_log.write, msg)

    def _scan_source_folder(self) -> None:
        source_str = self.query_one("#inp-source", Input).value.strip()
        scan_log = self.query_one("#scan-log", RichLog)
        scan_log.display = True
        scan_log.clear()

        if not source_str:
            scan_log.write("[red]No path entered.[/red]")
            return

        p = Path(source_str).resolve()
        if not p.exists():
            scan_log.write(f"[red]✘ Path does not exist: {p}[/red]")
            return
        if not p.is_dir():
            scan_log.write(f"[red]✘ Not a directory: {p}[/red]")
            return

        recursive = self._selected_index("rs-recursive") == 0
        scan_log.write(f"Scanning [bold]{p}[/bold] …")

        def _do_scan() -> None:
            raw_files = collect_raw_files(p, recursive)
            recurse_note = " (including subfolders)" if recursive else " (top-level only)"
            if raw_files:
                self._scan_log(f"[green]✔ {len(raw_files)} .raw file(s) found{recurse_note}[/green]")
            else:
                self._scan_log(f"[yellow]⚠ No .raw files found{recurse_note}[/yellow]")

        threading.Thread(target=_do_scan, daemon=True).start()

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def _download_tool(self, tool: str) -> None:
        if tool == "thermo":
            idx = self._selected_index("rs-thermo-ver")
            entry = THERMOCONVERT_VERSIONS[idx]
            status_id = "thermo-status"
            log_id = "thermo-log"
        else:
            idx = self._selected_index("rs-msconvert-ver")
            entry = MSCONVERT_VERSIONS[idx]
            status_id = "msconvert-status"
            log_id = "msconvert-log"

        inline_log = self.query_one(f"#{log_id}", RichLog)
        inline_log.clear()
        inline_log.write(f"[bold]Downloading {entry['label']}...[/bold]")

        def _progress(msg: str) -> None:
            il = self.query_one(f"#{log_id}", RichLog)
            self.call_from_thread(il.write, msg)

        def _do_download() -> None:
            ok, msg = install_tool(entry, progress_cb=_progress)
            self.call_from_thread(
                self.query_one(f"#{status_id}", Static).update,
                self._tool_status_text(tool, idx),
            )
            _progress(f"{'[green]✔ Done[/green]' if ok else '[red]✘ FAILED[/red]'}: {msg}")

        threading.Thread(target=_do_download, daemon=True).start()

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def _start_conversion(self) -> None:
        source_str = self.query_one("#inp-source", Input).value.strip()
        output_str = self.query_one("#inp-output", Input).value.strip()

        if not source_str or not output_str:
            self._log("[red]ERROR: Source and output folders must be set.[/red]")
            return

        raw_data_folder = Path(source_str).resolve()
        output_folder = Path(output_str).resolve()

        if not raw_data_folder.exists():
            self._log(f"[red]ERROR: Source folder does not exist: {raw_data_folder}[/red]")
            return

        recursive = self._selected_index("rs-recursive") == 0
        skip_existing = self._selected_index("rs-existing") == 0

        conv_idx = self._selected_index("rs-converter")
        converter = "thermo" if conv_idx == 0 else "msconvert"

        thermo_ver_idx = self._selected_index("rs-thermo-ver")
        msconvert_ver_idx = self._selected_index("rs-msconvert-ver")

        do_fix = (self._selected_index("rs-fix")) == 0

        newext_raw = self.query_one("#inp-newext", Input).value.strip()
        newext = newext_raw if newext_raw else "::SAME"

        ts_idx = self._selected_index("rs-timestamp")
        timestamp_mode: str | None = None
        if ts_idx == 1:
            timestamp_mode = "prefix"
        elif ts_idx == 2:
            timestamp_mode = "suffix"

        # --- Spectrum filters ---
        filter_ms_levels: set[int] = set()
        if self.query_one("#cb-filter-ms1", Checkbox).value:
            filter_ms_levels.add(1)
        if self.query_one("#cb-filter-ms2", Checkbox).value:
            filter_ms_levels.add(2)

        def _parse_float(widget_id: str) -> float | None:
            raw = self.query_one(widget_id, Input).value.strip()
            if not raw:
                return None
            try:
                return float(raw)
            except ValueError:
                self._log(f"[yellow]WARNING: Invalid number in {widget_id}, ignoring.[/yellow]")
                return None

        filter_ce_min = _parse_float("#inp-ce-min")
        filter_ce_max = _parse_float("#inp-ce-max")

        filter_ce_values: set[float] = set()
        ce_values_raw = self.query_one("#inp-ce-values", Input).value.strip()
        if ce_values_raw:
            for part in ce_values_raw.split(";"):
                part = part.strip()
                if part:
                    try:
                        filter_ce_values.add(float(part))
                    except ValueError:
                        self._log(f"[yellow]WARNING: Invalid CE value '{part}', ignoring.[/yellow]")

        filter_regex_raw = self.query_one("#inp-filter-regex", Input).value.strip()
        filter_string_regex: str | None = filter_regex_raw if filter_regex_raw else None

        mzml_filter = MzmlFilter(
            ms_levels=filter_ms_levels,
            ce_min=filter_ce_min,
            ce_max=filter_ce_max,
            ce_values=filter_ce_values,
            filter_string_regex=filter_string_regex,
        )

        threads_raw = self.query_one("#inp-threads", Input).value.strip()
        try:
            n_threads = max(1, int(threads_raw))
        except ValueError:
            n_threads = 4

        # Check tools are available
        thermoconvert, msconvert = get_tool_paths(thermo_ver_idx, msconvert_ver_idx)
        if not thermoconvert.exists():
            self._log(f"[red]ERROR: ThermoRawFileParser not found: {thermoconvert}[/red]")
            self._log("[yellow]Use the Download button to install it first.[/yellow]")
            return
        if converter == "msconvert" and not msconvert.exists():
            self._log(f"[red]ERROR: MSConvert not found: {msconvert}[/red]")
            self._log("[yellow]Use the Download button to install it first.[/yellow]")
            return

        log_widget = self.query_one("#log", RichLog)
        log_widget.clear()
        log_widget.write("[bold green]Starting conversion...[/bold green]")

        # Show and reset progress bar
        bar = self.query_one("#progress-bar", ProgressBar)
        label = self.query_one("#progress-label", Static)
        bar.display = True
        label.display = True
        bar.update(total=1, progress=0)
        label.update("Converting…")

        def _do_convert() -> None:
            try:
                run_conversion(
                    raw_data_folder=raw_data_folder,
                    output_folder=output_folder,
                    recursive=recursive,
                    converter=converter,
                    do_fix=do_fix,
                    newext=newext,
                    ppm_dev=1.0,
                    skip_existing=skip_existing,
                    n_threads=n_threads,
                    thermo_version_idx=thermo_ver_idx,
                    msconvert_version_idx=msconvert_ver_idx,
                    timestamp_mode=timestamp_mode,
                    mzml_filter=mzml_filter,
                    log_callback=self._log,
                    progress_callback=self._update_progress,
                )
            except Exception as exc:
                self._log(f"[red]ERROR: Conversion failed: {exc}[/red]")

        threading.Thread(target=_do_convert, daemon=True).start()
