"""Convert CSV files to Excel workbooks.

For each .csv in input/, reads it with pandas and writes an .xlsx to output/.
"""

import pandas as pd
import glob
import os

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Folder containing CSV files
input_folder = os.path.join(script_dir, 'input')
output_folder = os.path.join(script_dir, 'output')


def _round_trips(converted: pd.Series, original: pd.Series) -> bool:
    """Would printing the converted column back out give the original characters?"""
    filled = original.notna()
    return bool((converted[filled].map(str) == original[filled]).all())


def _infer_lossless(column: pd.Series) -> pd.Series:
    """Give a column its real type back, but only when nothing is lost by doing so.

    A CSV holds characters, not types, so pandas has to guess. Guessing per column is
    usually right and occasionally destructive: '007' is a product code, not the number
    seven, and 'TRUE' is a word before it is a boolean. Reading everything as text and
    handing it all to Excel as text avoids that but costs you a price column Excel can
    add up, so each column is converted only if printing it back gives exactly the
    characters that came in.
    """
    try:
        numeric = pd.to_numeric(column)
    except (ValueError, TypeError):
        return column

    # Nullable integer first. A single blank cell forces plain to_numeric to float,
    # which would write 1 as 1.0.
    try:
        as_int = numeric.astype("Int64")
    except (ValueError, TypeError):
        as_int = None

    for candidate in (as_int, numeric):
        if candidate is not None and _round_trips(candidate, column):
            return candidate
    return column


def convert_csv_to_xlsx() -> str:
    """Convert all CSV files in the input folder to XLSX files in the output folder.

    Returns:
        A summary of what was converted, suitable for showing to a caller.
    """
    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    # Find all .csv files in the folder
    csv_files = glob.glob(os.path.join(input_folder, '*.csv'))

    if not csv_files:
        # If only .xlsx files are present, notify they're already Excel
        xlsx_present = glob.glob(os.path.join(input_folder, '*.xlsx'))
        if xlsx_present:
            return "That file is already in Excel format"
        return "No CSV files found in input folder"

    print(f"Found {len(csv_files)} CSV file(s)")

    converted = []
    errors = []

    for file in csv_files:
        # Get just the filename (outside the try so it's always available for errors)
        filename = os.path.basename(file)

        try:
            # Create output Excel filename
            xlsx_filename = os.path.splitext(filename)[0] + '.xlsx'
            xlsx_path = os.path.join(output_folder, xlsx_filename)

            # Read as text so pandas' own guessing can't damage anything, then put back
            # only the types that survive being printed out again.
            df = pd.read_csv(file, dtype=str).apply(_infer_lossless)

            # xlsxwriter rather than the default openpyxl. openpyxl stores any string
            # starting with '=' as a live formula, which both loses the original text
            # and hands the user a workbook their spreadsheet will execute on open.
            with pd.ExcelWriter(
                xlsx_path,
                engine="xlsxwriter",
                engine_kwargs={"options": {"strings_to_formulas": False}},
            ) as writer:
                df.to_excel(writer, index=False)
            print(f"Converted {filename} to {xlsx_filename}")
            converted.append(xlsx_filename)

        except Exception as e:
            print(f"Error converting {filename}: {e}")
            errors.append(f"{filename}: {e}")

    if not converted:
        return f"No files converted. {len(errors)} failed: {'; '.join(errors)}"

    summary = f"Converted {len(converted)} file(s) to output/: {', '.join(converted)}"
    if errors:
        summary += f". {len(errors)} failed: {'; '.join(errors)}"
    return summary


if __name__ == "__main__":
    print(convert_csv_to_xlsx())
