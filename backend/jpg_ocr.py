"""Convert JPG/JPEG images to plain text via OCR.

For each image in input/, converts it to RGB, runs Tesseract OCR (through a
temporary PNG), and writes the extracted text to output/.

English only: Tesseract is called with lang='eng', so text in another language comes
back as whatever English words its shapes resemble rather than as an error.
"""

import os
import glob
import pytesseract
import shutil
from PIL import Image

# Dynamically find tesseract executable
tesseract_path = shutil.which('tesseract')
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
else:
    print("Warning: tesseract not found in PATH. Make sure tesseract is installed and accessible.")

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Folders
input_folder = os.path.join(script_dir, 'input')
output_folder = os.path.join(script_dir, 'output')


def convert_jpg_to_ocr() -> str:
    """Convert all JPG/JPEG files in the input folder to text files using OCR.

    Returns:
        A summary of what was converted, suitable for showing to a caller.
    """

    # Create output folder if it doesn't exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Find all JPG/JPEG files
    jpg_files = glob.glob(os.path.join(input_folder, '*.jpg')) + \
                glob.glob(os.path.join(input_folder, '*.jpeg'))

    if not jpg_files:
        # If there are only text files present, notify the user those are already in target format
        txt_present = glob.glob(os.path.join(input_folder, '*.txt'))
        if txt_present:
            return "That file is already in text format"
        return "No JPG/JPEG files found in input folder"

    print(f"Found {len(jpg_files)} JPG/JPEG files to convert")

    converted = []
    errors = []

    for jpg_file in jpg_files:
        try:
            # Get filename without extension
            filename = os.path.splitext(os.path.basename(jpg_file))[0]
            txt_file = os.path.join(output_folder, f"{filename}.txt")
            
            # Open image and perform OCR
            with Image.open(jpg_file) as img:
                # Convert to RGB if needed
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Save as a temporary PNG for tesseract compatibility
                temp_png = os.path.join(output_folder, f"{filename}_temp.png")
                img.save(temp_png, 'PNG')
                
                # Use pytesseract to extract text with better settings for accuracy
                custom_config = r'--oem 3 --psm 6'
                text = pytesseract.image_to_string(temp_png, config=custom_config, lang='eng')
                
                # Clean up temporary PNG
                os.remove(temp_png)
                
                # Clean up extra whitespace
                text = text.strip()
                
                # Save as text file
                with open(txt_file, 'w', encoding='utf-8') as f:
                    f.write(text)
                
                print(f"Converted: {os.path.basename(jpg_file)} -> {filename}.txt")
                converted.append(f"{filename}.txt")

        except Exception as e:
            print(f"Error converting {jpg_file}: {str(e)}")
            errors.append(f"{os.path.basename(jpg_file)}: {e}")

    if not converted:
        return f"No files converted. {len(errors)} failed: {'; '.join(errors)}"

    summary = f"Converted {len(converted)} file(s) to output/: {', '.join(converted)}"
    if errors:
        summary += f". {len(errors)} failed: {'; '.join(errors)}"
    return summary


if __name__ == "__main__":
    print(convert_jpg_to_ocr())
