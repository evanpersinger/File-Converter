"""Convert Excel workbooks to CSV.

For each .xlsx in input/, reads it with pandas and writes a .csv to output/.
"""

import pandas as pd
import glob
import os

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Folder containing Excel files
input_folder = os.path.join(script_dir, 'input')
output_folder = os.path.join(script_dir, 'output')


def convert_xlsx_to_csv() -> str:
    """Convert all XLSX files in the input folder to CSV files in the output folder.

    Returns:
        A summary of what was converted, suitable for showing to a caller.
    """
    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    # Find all .xlsx files in the folder
    excel_files = glob.glob(os.path.join(input_folder, '*.xlsx'))

    if not excel_files:
        # If only CSVs are present, notify they're already CSV
        csv_present = glob.glob(os.path.join(input_folder, '*.csv'))
        if csv_present:
            return "That file is already in csv format"
        return "No Excel files found in input folder"

    print(f"Found {len(excel_files)} Excel file(s)")

    converted = []
    errors = []

    for file in excel_files:
        # Get just the filename (outside the try so it's always available for errors)
        filename = os.path.basename(file)

        try:
            # Create output CSV filename
            csv_filename = os.path.splitext(filename)[0] + '.csv'
            csv_path = os.path.join(output_folder, csv_filename)

            # dtype=str keeps the cell types the workbook already declares. Without it
            # pandas re-guesses them, and a cell explicitly stored as text comes back
            # as something else: '007' as the number 7, 'TRUE' as the word True. There
            # is nothing to lose by reading as text here, since the output is a CSV and
            # a CSV carries no types either way.
            df = pd.read_excel(file, dtype=str)
            df.to_csv(csv_path, index=False)
            print(f"Converted {filename} to {csv_filename}")
            converted.append(csv_filename)

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
    print(convert_xlsx_to_csv())
