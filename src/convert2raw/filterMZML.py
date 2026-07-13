"""Post-conversion mzML spectrum filter.

Parses an mzML file and removes spectra that do not match the
specified filter criteria, then writes the filtered mzML back in-place.
All active criteria are combined with AND logic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import bs4

# ---------------------------------------------------------------------------
# CV accession constants
# ---------------------------------------------------------------------------
_CV_NEGATIVE_SCAN = "MS:1000129"
_CV_POSITIVE_SCAN = "MS:1000130"
_CV_MS_LEVEL = "MS:1000511"
_CV_COLLISION_ENERGY = "MS:1000045"
_CV_FILTER_STRING = "MS:1000512"


# ---------------------------------------------------------------------------
# Filter configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class MzmlFilter:
    """Criteria for post-conversion mzML spectrum filtering.

    Attributes:
        polarity:             None = keep all; "positive" / "negative" = keep only that polarity.
        ms_levels:            Set of MS levels to keep (e.g. {1, 2}). Empty = keep all.
        ce_min:               Minimum collision energy (eV, inclusive). None = no lower bound.
        ce_max:               Maximum collision energy (eV, inclusive). None = no upper bound.
        ce_values:            Exact CE values to keep (eV, matched within 0.01 eV tolerance).
                              If non-empty, a spectrum passes the CE check when its CE matches
                              any value in this set OR falls within [ce_min, ce_max] (if set).
        filter_string_regex:  Regex applied to the filter string CV param value. None = no filter.
    """

    polarity: str | None = None
    ms_levels: set[int] = field(default_factory=set)
    ce_min: float | None = None
    ce_max: float | None = None
    ce_values: set[float] = field(default_factory=set)
    filter_string_regex: str | None = None

    def is_active(self) -> bool:
        """Return True if at least one criterion is active."""
        return (
            self.polarity is not None or bool(self.ms_levels) or self.ce_min is not None or self.ce_max is not None or bool(self.ce_values) or self.filter_string_regex is not None
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_cv(spectrum: bs4.Tag, accession: str) -> bs4.Tag | None:
    """Return the first cvParam with *accession* inside *spectrum*, or None."""
    return spectrum.find("cvParam", {"accession": accession})


def _spectrum_matches(spectrum: bs4.Tag, f: MzmlFilter) -> bool:
    """Return True if *spectrum* satisfies every active criterion in *f*."""

    # --- Polarity ---
    if f.polarity == "positive":
        if not _get_cv(spectrum, _CV_POSITIVE_SCAN):
            return False
    elif f.polarity == "negative":
        if not _get_cv(spectrum, _CV_NEGATIVE_SCAN):
            return False

    # --- MS level ---
    if f.ms_levels:
        cv = _get_cv(spectrum, _CV_MS_LEVEL)
        if cv is None:
            return False
        try:
            if int(cv["value"]) not in f.ms_levels:
                return False
        except (KeyError, ValueError):
            return False

    # --- Collision energy ---
    _ce_range_active = f.ce_min is not None or f.ce_max is not None
    _ce_values_active = bool(f.ce_values)
    if _ce_range_active or _ce_values_active:
        cv = _get_cv(spectrum, _CV_COLLISION_ENERGY)
        if cv is None:
            return False
        try:
            ce = float(cv["value"])
        except (KeyError, ValueError):
            return False
        # A spectrum passes if it satisfies the range OR matches one of the exact values
        in_range = (f.ce_min is None or ce >= f.ce_min) and (f.ce_max is None or ce <= f.ce_max)
        in_values = any(abs(ce - v) < 0.01 for v in f.ce_values)
        if _ce_range_active and _ce_values_active:
            if not (in_range or in_values):
                return False
        elif _ce_range_active:
            if not in_range:
                return False
        else:
            if not in_values:
                return False

    # --- Filter string regex ---
    if f.filter_string_regex is not None:
        cv = _get_cv(spectrum, _CV_FILTER_STRING)
        val = cv.get("value", "") if cv is not None else ""
        try:
            if not re.search(f.filter_string_regex, val):
                return False
        except re.error:
            return False

    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def apply_mzml_filter(mzml_file: Path, f: MzmlFilter, log: list[str] | None = None) -> None:
    """Filter spectra in *mzml_file* in-place according to *f*.

    Spectra that do not satisfy all active criteria are removed.
    The ``count`` attribute of ``<spectrumList>`` and the ``index``
    attributes of remaining spectra are updated accordingly.
    The ``<indexList>`` (byte-offset index) is removed because byte
    offsets are invalidated by the re-serialisation; all major mzML
    readers fall back to linear scanning when the index is absent.
    """
    if not f.is_active():
        return

    def _log(msg: str) -> None:
        if log is None:
            print(msg)
        else:
            log.append(msg)

    _log(f"  Filtering spectra: {mzml_file.name}")

    with open(mzml_file, "r", encoding="utf-8") as fh:
        data = fh.read()

    soup = bs4.BeautifulSoup(data, "xml")

    spectrum_list = soup.find("spectrumList")
    if spectrum_list is None:
        _log("  WARNING: No <spectrumList> found, skipping filter.")
        return

    spectra = spectrum_list.find_all("spectrum", recursive=False)
    kept = 0
    removed = 0
    for sp in spectra:
        if _spectrum_matches(sp, f):
            sp["index"] = str(kept)
            kept += 1
        else:
            sp.decompose()
            removed += 1

    spectrum_list["count"] = str(kept)

    # Remove the byte-offset index — it is invalidated by the rewrite
    index_list = soup.find("indexList")
    if index_list is not None:
        index_list.decompose()
    index_list_offset = soup.find("indexListOffset")
    if index_list_offset is not None:
        index_list_offset.decompose()
    file_checksum = soup.find("fileChecksum")
    if file_checksum is not None:
        file_checksum.decompose()

    _log(f"  Filter result: kept {kept}, removed {removed} spectrum/spectra.")

    with open(mzml_file, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            re.sub(
                "<binary>\\s*(.*)\\s*</binary>",
                "<binary>\\1</binary>",
                soup.prettify().replace("\r", ""),
            )
        )
