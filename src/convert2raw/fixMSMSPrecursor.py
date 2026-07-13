# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "beautifulsoup4", "lxml"
# ]
# ///

import bs4
import re
from os import listdir
from os.path import isfile, join
import argparse


def commentWrongPrecursorInfo(file, newFileExtension=""):
    ## Reading data from the xml file
    with open(file, "r") as f:
        data = f.read()

    ## Parse XML
    bs_data = bs4.BeautifulSoup(data, "xml")

    ## Find tags to comment them ## suggestion by Bernhard Seidl, thanks!
    ## <cvParam cvRef="MS" accession="MS:1000744" name="selected ion m/z"
    toDel = []
    for tag in bs_data.find_all(
        "cvParam",
        {"cvRef": "MS", "accession": "MS:1000744", "name": "selected ion m/z"},
    ):
        toDel.append(tag)
        tag.decompose()
        # tag.replace_with(bs4.Comment(str(tag)))
    print("      .. commented %d precursor information tags (selected ion m/z)" % (len(toDel)))

    with open(file.replace(".mzML", "%s.mzML" % (newFileExtension)), "w", newline="\n") as fout:
        fout.write(
            re.sub(
                "<binary>\\s*(.*)\\s*</binary>",
                "<binary>\\1</binary>",
                bs_data.prettify().replace("\r", ""),
            )
        )


def correctWrongPrecursorInfo(file, new_file_suffix="", ppm_dev=1.0):
    ## Reading data from the xml file
    with open(file, "r") as f:
        data = f.read()

    ## Parse XML
    bs_data = bs4.BeautifulSoup(data, "xml")

    changedMSMSScans = 0
    for tag in bs_data.find_all("precursor"):
        ## incorrect MS:1000744
        selMZ = tag.find_all(
            name="cvParam",
            attrs={
                "cvRef": "MS",
                "accession": "MS:1000744",
                "name": "selected ion m/z",
            },
            recursive=True,
        )
        ## correct MS:1000827
        isoMZ = tag.find_all(
            name="cvParam",
            attrs={
                "cvRef": "MS",
                "accession": "MS:1000827",
                "name": "isolation window target m/z",
            },
            recursive=True,
        )

        if len(selMZ) == 1 and len(isoMZ) == 1:
            selMZV = float(selMZ[0]["value"])
            isoMZV = float(isoMZ[0]["value"])

            if abs(selMZV - isoMZV) / isoMZV * 1e6 >= ppm_dev:
                print("      .. incorrect 'selected ion m/z' %.5f, correcting to 'isolation window target m/z' %.5f" % (selMZV, isoMZV))
                selMZ[0]["value"] = isoMZV
                changedMSMSScans += 1
        else:
            raise RuntimeError("There are 0 or more than 1 tag of 'selected ion m/z' or 'isolation window target m/z' for the tag: '%s'" % (tag))

    print("      .. corrected %d precursor information tags ('selected ion m/z' replaced with 'isolation window target m/z')" % (changedMSMSScans))

    output_file = file
    if new_file_suffix != "" and new_file_suffix != "::SAME":
        output_file = file.replace(".mzML", "%s.mzML" % (new_file_suffix))
    with open(output_file, "w", newline="\n") as fout:
        fout.write(
            re.sub(
                "<binary>\\s*(.*)\\s*</binary>",
                "<binary>\\1</binary>",
                bs_data.prettify().replace("\r", ""),
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Correct selected ion m/z tags in mzML files.")
    parser.add_argument(
        "--file",
        type=str,
        help="Path to the mzML file or directory containing mzML files.",
    )
    parser.add_argument(
        "--new_file_suffix",
        type=str,
        default="",
        help="Suffix to add to the new mzML files (optional, default: overwrite files).",
    )
    parser.add_argument(
        "--ppm_dev",
        type=float,
        default=1.0,
        help="PPM deviation threshold for correction (optional, default: 1.0).",
    )

    args = parser.parse_args()

    path = args.file
    new_file_suffix = args.new_file_suffix
    ppm_dev = args.ppm_dev

    print("Correcting 'selected ion m/z' tags from mzML files in '%s'" % (path))
    if new_file_suffix != "" and new_file_suffix != "::SAME":
        print("   .. adding the file extension '%s'.mzML to the corrected files" % new_file_suffix)
    else:
        print("   .. files will be overwritten")
    print("   .. using a ppm deviation of %.2f" % ppm_dev)

    if isfile(path) and path.lower().endswith(".mzml"):
        print("   .. processing file '%s'" % (path))
        correctWrongPrecursorInfo(path, new_file_suffix=new_file_suffix, ppm_dev=ppm_dev)

    elif not isfile(path):
        for file in listdir(path):
            if isfile(join(path, file)) and file.lower().endswith(".mzml"):
                print("   .. processing file '%s'" % (file))
                correctWrongPrecursorInfo(join(path, file), new_file_suffix=new_file_suffix, ppm_dev=ppm_dev)
    else:
        print("given --file '%s' is not a file or does not end with '.mzml'" % (path))

    print("")
