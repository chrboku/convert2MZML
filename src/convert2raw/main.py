import shutil
import subprocess
import tarfile
import tempfile
import threading
import urllib.request
import zipfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import toml

from .filterMZML import MzmlFilter, apply_mzml_filter  # noqa: E402
from .fixMSMSPrecursor import correctWrongPrecursorInfo  # noqa: E402
from .prefixTimestamp import rename_mzml_with_timestamp  # noqa: E402

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent.parent.parent.resolve()

# ---------------------------------------------------------------------------
# Tool version registry
# Each entry: {"label": str, "url": str, "exe_rel": str, "archive_type": "zip"|"tar.bz2"}
# exe_rel is the path of the executable *relative to the sw/ folder*.
# Add new versions by appending to these lists — the TUI will show them.
# ---------------------------------------------------------------------------

THERMOCONVERT_VERSIONS: list[dict] = [
    {
        "label": "ThermoRawFileParser v2.0.0-dev",
        "url": "https://github.com/CompOmics/ThermoRawFileParser/releases/download/v.2.0.0-dev/ThermoRawFileParser-v.2.0.0-dev-win.zip",
        "exe_rel": "ThermoRawFileParser_2.0.0-dev-win/ThermoRawFileParser.exe",
        "archive_type": "zip",
    },
    {
        "label": "ThermoRawFileParser v1.4.5",
        "url": "https://github.com/CompOmics/ThermoRawFileParser/releases/download/v1.4.5/ThermoRawFileParser1.4.5.zip",
        "exe_rel": "ThermoRawFileParser_1.4.5/ThermoRawFileParser.exe",
        "archive_type": "zip",
    },
    {
        "label": "ThermoRawFileParser v1.4.3",
        "url": "https://github.com/CompOmics/ThermoRawFileParser/releases/download/v1.4.3/ThermoRawFileParser1.4.3.zip",
        "exe_rel": "ThermoRawFileParser_1.4.3/ThermoRawFileParser.exe",
        "archive_type": "zip",
    },
]

MSCONVERT_VERSIONS: list[dict] = [
    {
        "label": "MSConvert / ProteoWizard 3.0.26123",
        "url": "https://mc-tca-01.s3.us-west-2.amazonaws.com/ProteoWizard/bt83/3969548/pwiz-bin-windows-x86_64-vc145-release-3_0_26123_e5a25cb.tar.bz2",
        "exe_rel": "ProteoWizard-x86_64-vc145-release-3_0_26123_e5a25cb/msconvert.exe",
        "archive_type": "tar.bz2",
    },
    # {
    #    "label": "MSConvert / ProteoWizard 3.0.26102",
    #    "url": "https://mc-tca-01.s3.us-west-2.amazonaws.com/ProteoWizard/bt83/3934453/pwiz-bin-windows-x86_64-vc145-release-3_0_26102_0783ec5.tar.bz2",
    #    "exe_rel": "ProteoWizard-x86_64-vc145-release-3_0_26102_0783ec5/msconvert.exe",
    #    "archive_type": "tar.bz2",
    # },
    # {
    #    "label": "MSConvert / ProteoWizard 3.0.25149",
    #    "url": "https://mc-tca-01.s3.us-west-2.amazonaws.com/ProteoWizard/bt83/3813985/pwiz-bin-windows-x86_64-vc145-release-3_0_25149_2e8a3d7.tar.bz2",
    #    "exe_rel": "ProteoWizard-x86_64-vc145-release-3_0_25149_2e8a3d7/msconvert.exe",
    #    "archive_type": "tar.bz2",
    # },
]


def get_tool_paths(thermo_idx: int = 0, msconvert_idx: int = 0) -> tuple[Path, Path]:
    """Return (thermoconvert_exe, msconvert_exe) for the given version indices."""
    t = THERMOCONVERT_VERSIONS[thermo_idx]
    m = MSCONVERT_VERSIONS[msconvert_idx]
    return (
        SCRIPT_DIR / "sw" / t["exe_rel"],
        SCRIPT_DIR / "sw" / m["exe_rel"],
    )


SEP = "-" * 79
_print_lock = threading.Lock()


def log_append(log: list[str] | None, msg: str) -> None:
    if log is None:
        print(msg)
    else:
        log.append(msg)


# ---------------------------------------------------------------------------
# Download / install helpers
# ---------------------------------------------------------------------------


def _download_with_progress(url: str, dest: Path, label: str, progress_cb: Callable[[str], None] | None = None) -> None:
    def _report(block_count: int, block_size: int, total_size: int) -> None:
        if total_size > 0:
            pct = min(100, block_count * block_size * 100 // total_size)
            msg = f"Downloading {label}: {pct:3d}%"
        else:
            downloaded = block_count * block_size
            msg = f"Downloading {label}: {downloaded // 1024} KB"
        if progress_cb:
            progress_cb(msg)
        else:
            print(f"\r    {msg}", end="", flush=True)

    if progress_cb:
        progress_cb(f"Starting download: {label}")
    else:
        print(f"  Downloading {label} from:\n    {url}")
    urllib.request.urlretrieve(url, dest, reporthook=_report)
    if not progress_cb:
        print()


def install_tool(version_entry: dict, progress_cb: Callable[[str], None] | None = None) -> tuple[bool, str]:
    """
    Download and install a tool from *version_entry*.
    Returns (success, message).
    """
    exe_path = SCRIPT_DIR / "sw" / version_entry["exe_rel"]
    target_dir = exe_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    url: str = version_entry["url"]
    archive_type: str = version_entry["archive_type"]
    label: str = version_entry["label"]

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / Path(url.split("/")[-1])
        try:
            _download_with_progress(url, archive, label, progress_cb)
        except Exception as exc:
            return False, f"Download failed: {exc}"

        if progress_cb:
            progress_cb(f"Extracting {label} ...")
        else:
            print(f"  Extracting to {target_dir} ...")

        try:
            if archive_type == "zip":
                with zipfile.ZipFile(archive) as zf:
                    zf.extractall(target_dir)
            elif archive_type == "tar.bz2":
                with tarfile.open(archive, "r:bz2") as tf:
                    for member in tf.getmembers():
                        parts = Path(member.name).parts
                        member.name = str(Path(*parts[1:])) if len(parts) > 1 else member.name
                    tf.extractall(target_dir)
            else:
                return False, f"Unknown archive type: {archive_type}"
        except Exception as exc:
            return False, f"Extraction failed: {exc}"

    if not exe_path.exists():
        return False, f"Executable not found after extraction: {exe_path}"

    msg = f"{label} installed at {exe_path}"
    if progress_cb:
        progress_cb(msg)
    else:
        print(f"  {msg}")
    return True, msg


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def collect_raw_files(source_folder: Path, recursive: bool) -> list[Path]:
    pattern = "**/*.raw" if recursive else "*.raw"
    return sorted(source_folder.glob(pattern))


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def output_dir_for(raw_file: Path, source_folder: Path, output_base: Path, mode_subdir: str) -> Path:
    rel_parent = raw_file.relative_to(source_folder).parent
    return output_base / mode_subdir / rel_parent


def convert_thermo(raw_file: Path, out_dir: Path, thermoconvert: Path, log: list[str] | None = None) -> None:
    ensure_dir(out_dir)
    cmd = [str(thermoconvert), "-f", "1", "-a", "-e", "-x", "-i", str(raw_file), "-o", str(out_dir)]
    log_append(log, f"  Converting (ThermoRawFileParser): {raw_file.name}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    for line in (result.stdout or "").splitlines():
        log_append(log, f"    {line}")
    for line in (result.stderr or "").splitlines():
        log_append(log, f"    {line}")
    if result.returncode != 0:
        log_append(log, f"  WARNING: Converter returned exit code {result.returncode} for '{raw_file.name}'")


def convert_msconvert(raw_file: Path, out_dir: Path, msconvert: Path, polarity_filter: str | None = None, log: list[str] | None = None) -> None:
    ensure_dir(out_dir)
    cmd = [str(msconvert), str(raw_file), "--mzML", "--zlib", "-v"]
    if polarity_filter:
        cmd += ["--filter", f"polarity {polarity_filter}"]
    cmd += ["peakPicking true 1-"]
    cmd += ["-o", str(out_dir), "--ignoreUnknownInstrumentError"]
    log_append(log, f"  Converting (MSConvert): {raw_file.name}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    for line in (result.stdout or "").splitlines():
        log_append(log, f"    {line}")
    for line in (result.stderr or "").splitlines():
        log_append(log, f"    {line}")
    if result.returncode != 0:
        log_append(log, f"  WARNING: Converter returned exit code {result.returncode} for '{raw_file.name}'")


def fix_msms(mzml_file: Path, new_file_suffix: str, ppm_dev: float, log: list[str] | None = None) -> Path:
    """Fix MSMS precursors and return the (possibly renamed) output file path."""
    if not mzml_file.exists():
        log_append(log, f"  WARNING: Expected output file not found, skipping MSMS fix: {mzml_file}")
        return mzml_file
    log_append(log, f"  Fixing MSMS precursors: {mzml_file.name}")
    suffix = "" if new_file_suffix == "::SAME" else new_file_suffix
    try:
        correctWrongPrecursorInfo(str(mzml_file), new_file_suffix=suffix, ppm_dev=ppm_dev)
    except Exception as exc:
        log_append(log, f"  WARNING: MSMS fix failed for '{mzml_file.name}': {exc}")
        return mzml_file
    if suffix:
        new_path = mzml_file.parent / (mzml_file.stem + suffix + ".mzML")
        try:
            mzml_file.unlink()
        except Exception as exc:
            log_append(log, f"  WARNING: Could not remove original file '{mzml_file.name}': {exc}")
        return new_path
    return mzml_file


def process_job(job: dict, log_callback: Callable[[str], None] | None = None) -> None:
    """
    Convert one raw file, optionally fix MSMS precursors, and optionally prefix
    the output filename with the acquisition timestamp.  Thread-safe.
    """
    raw_file: Path = job["raw_file"]
    out_dir: Path = job["out_dir"]
    converter: str = job["converter"]
    polarity_filter: str | None = job["polarity_filter"]
    do_fix: bool = job["fix"]
    newext: str = job["newext"]
    ppm_dev: float = job["ppm_dev"]
    label: str = job["label"]
    thermoconvert: Path = job["thermoconvert"]
    msconvert: Path = job["msconvert"]
    timestamp_mode: str | None = job.get("timestamp_mode", None)
    mzml_filter: MzmlFilter = job.get("mzml_filter", MzmlFilter())

    log: list[str] = []

    def _emit(msg: str) -> None:
        log.append(msg)
        if log_callback:
            log_callback(msg)

    _emit(f"[{label}] START: {raw_file.name}")

    if converter == "thermo":
        convert_thermo(raw_file, out_dir, thermoconvert, log=log)
    else:
        convert_msconvert(raw_file, out_dir, msconvert, polarity_filter=polarity_filter, log=log)

    mzml_file = out_dir / (raw_file.stem + ".mzML")

    if do_fix:
        mzml_file = fix_msms(mzml_file, newext, ppm_dev, log=log)

    if timestamp_mode in ("prefix", "suffix"):
        new_path = rename_mzml_with_timestamp(mzml_file, position=timestamp_mode, log=log)
        if new_path:
            mzml_file = new_path

    if mzml_filter.is_active():
        apply_mzml_filter(mzml_file, mzml_filter, log=log)

    _emit(f"[{label}] DONE:  {raw_file.name}")

    if not log_callback:
        with _print_lock:
            for line in log:
                print(line)


# ---------------------------------------------------------------------------
# Build job list
# ---------------------------------------------------------------------------


def build_jobs(
    raw_files: list[Path],
    raw_data_folder: Path,
    output_folder: Path,
    converter: str,
    exp_fps: bool,
    exp_pos: bool,
    exp_neg: bool,
    do_fix: bool,
    newext: str,
    ppm_dev: float,
    thermoconvert: Path,
    msconvert: Path,
    timestamp_mode: str | None = None,
    mzml_filter: MzmlFilter | None = None,
) -> list[dict]:
    jobs: list[dict] = []
    common = dict(
        fix=do_fix,
        newext=newext,
        ppm_dev=ppm_dev,
        thermoconvert=thermoconvert,
        msconvert=msconvert,
        timestamp_mode=timestamp_mode,
        mzml_filter=mzml_filter or MzmlFilter(),
    )

    if converter == "thermo":
        for raw_file in raw_files:
            out_dir = output_dir_for(raw_file, raw_data_folder, output_folder, "FPS")
            jobs.append(dict(raw_file=raw_file, out_dir=out_dir, converter="thermo", polarity_filter=None, label="FPS", **common))
    else:
        modes: list[tuple[str, str | None]] = []
        if exp_fps:
            modes.append(("FPS", None))
        if exp_pos:
            modes.append(("pos", "positive"))
        if exp_neg:
            modes.append(("neg", "negative"))
        for mode_dir, polarity in modes:
            for raw_file in raw_files:
                out_dir = output_dir_for(raw_file, raw_data_folder, output_folder, mode_dir)
                jobs.append(dict(raw_file=raw_file, out_dir=out_dir, converter="msconvert", polarity_filter=polarity, label=mode_dir, **common))

    return jobs


def filter_existing_jobs(jobs: list[dict]) -> tuple[list[dict], int]:
    """Return (remaining_jobs, n_skipped) based on whether the output mzML exists."""

    def _output_mzml(job: dict) -> Path:
        stem = job["raw_file"].stem
        if job["fix"] and job["newext"] != "::SAME":
            return job["out_dir"] / (stem + job["newext"] + ".mzML")
        return job["out_dir"] / (stem + ".mzML")

    remaining = [j for j in jobs if not _output_mzml(j).exists()]
    return remaining, len(jobs) - len(remaining)


# ---------------------------------------------------------------------------
# Top-level conversion runner (called by TUI)
# ---------------------------------------------------------------------------


def run_conversion(
    raw_data_folder: Path,
    output_folder: Path,
    recursive: bool,
    converter: str,
    exp_fps: bool,
    exp_pos: bool,
    exp_neg: bool,
    do_fix: bool,
    newext: str,
    ppm_dev: float,
    skip_existing: bool,
    n_threads: int,
    thermo_version_idx: int,
    msconvert_version_idx: int,
    timestamp_mode: str | None = None,
    mzml_filter: MzmlFilter | None = None,
    log_callback: Callable[[str], None] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> None:
    """Execute the full conversion pipeline."""

    def _log(msg: str) -> None:
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    thermoconvert, msconvert = get_tool_paths(thermo_version_idx, msconvert_version_idx)

    missing = []
    if not thermoconvert.exists():
        missing.append(f"ThermoRawFileParser not found at: {thermoconvert}")
    if converter == "msconvert" and not msconvert.exists():
        missing.append(f"MSConvert not found at: {msconvert}")
    if missing:
        for m in missing:
            _log(f"ERROR: {m}")
        return

    if output_folder.exists() and not skip_existing:
        shutil.rmtree(output_folder)

    raw_files = collect_raw_files(raw_data_folder, recursive)
    if not raw_files:
        _log("No .raw files found in the source folder.")
        return

    _log(f"Found {len(raw_files)} .raw file(s).")

    jobs = build_jobs(
        raw_files=raw_files,
        raw_data_folder=raw_data_folder,
        output_folder=output_folder,
        converter=converter,
        exp_fps=exp_fps,
        exp_pos=exp_pos,
        exp_neg=exp_neg,
        do_fix=do_fix,
        newext=newext,
        ppm_dev=ppm_dev,
        thermoconvert=thermoconvert,
        msconvert=msconvert,
        timestamp_mode=timestamp_mode,
        mzml_filter=mzml_filter,
    )

    if skip_existing:
        jobs, skipped = filter_existing_jobs(jobs)
        if skipped:
            _log(f"Skipping {skipped} already-converted file(s).")

    if not jobs:
        _log("No files to process.")
        return

    _log(f"Processing {len(jobs)} job(s) with {n_threads} thread(s)...")

    total = len(jobs)
    completed_count = [0]
    lock = threading.Lock()

    def _run_job(job: dict) -> None:
        process_job(job, log_callback=log_callback)
        with lock:
            completed_count[0] += 1
            done = completed_count[0]
            _log(f"Progress: {done}/{total} done")
            if progress_callback:
                progress_callback(done, total)

    with ThreadPoolExecutor(max_workers=n_threads) as executor:
        executor.map(_run_job, jobs)

    _log("All done.")


# ---------------------------------------------------------------------------
# Version helper
# ---------------------------------------------------------------------------


def get_version() -> str:
    try:
        return toml.load(SCRIPT_DIR / "pyproject.toml")["project"]["version"]
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Entry point — launch TUI
# ---------------------------------------------------------------------------


def main() -> None:
    from .tui import Convert2RawApp

    app = Convert2RawApp()
    app.run()


if __name__ == "__main__":
    main()
