"""Convert JPG/JPEG images to Markdown via OCR.

For each image in input/, preprocesses it (grayscale, contrast, sharpen, denoise),
runs Tesseract OCR, cleans up the text (rejoining split sentences), and writes it
to output/.

English only: Tesseract is called with lang='eng', so text in another language comes
back as whatever English words its shapes resemble rather than as an error.
"""

import os
import glob
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import re

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Folders
input_folder = os.path.join(script_dir, 'input')
output_folder = os.path.join(script_dir, 'output')


def preprocess_image(image):
    """Preprocess image to improve OCR accuracy"""
    # Convert to grayscale for better OCR
    if image.mode != 'L':
        image = image.convert('L')
    
    # Enhance contrast
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.5)
    
    # Enhance sharpness
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(1.2)
    
    # Apply slight denoising
    image = image.filter(ImageFilter.MedianFilter(size=3))
    
    return image


def clean_text(text):
    """Clean extracted text and format as markdown"""
    if not text:
        return ""
    
    # Remove excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Remove trailing whitespace from each line
    lines = [line.rstrip() for line in text.split('\n')]
    
    # Join lines that are clearly part of the same sentence
    fixed_lines = []
    i = 0
    while i < len(lines):
        current_line = lines[i]
        
        if not current_line.strip():
            fixed_lines.append(current_line)
            i += 1
            continue
        
        # Try to join with following lines that are continuations
        while i + 1 < len(lines):
            next_line = lines[i + 1]
            
            if not next_line.strip():
                break
            
            next_stripped = next_line.strip()
            starts_with_lowercase = next_stripped and next_stripped[0].islower()
            ends_with_continuation = re.search(r'[,;:—–-]\s*$', current_line)
            
            should_join = False
            if starts_with_lowercase:
                should_join = True
            elif ends_with_continuation and next_stripped and not next_stripped[0].isupper():
                should_join = True
            
            if should_join:
                current_line = current_line + ' ' + next_stripped
                i += 1
            else:
                break
        
        fixed_lines.append(current_line)
        i += 1
    
    text = '\n'.join(fixed_lines)
    
    # Final cleanup
    text = re.sub(r' +', ' ', text)
    text = re.sub(r'\n +', '\n', text)
    
    return text.strip()


def convert_jpg_to_markdown() -> str:
    """Convert all JPG files in the input folder to Markdown files in the output folder.

    Uses OCR, so this reads text straight out of the image.

    Returns:
        A summary of what was converted, suitable for showing to a caller.
    """

    # Create output folder if it doesn't exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Find all JPG files
    jpg_files = glob.glob(os.path.join(input_folder, '*.jpg')) + \
                glob.glob(os.path.join(input_folder, '*.jpeg'))

    if not jpg_files:
        # If there are only markdown files present, notify the user
        md_present = glob.glob(os.path.join(input_folder, '*.md'))
        if md_present:
            return "That file is already in markdown format"
        return "No JPG files found in input folder"

    print(f"Found {len(jpg_files)} JPG files to convert")

    converted = []
    errors = []

    for jpg_file in jpg_files:
        try:
            # Get filename without extension
            filename = os.path.splitext(os.path.basename(jpg_file))[0]
            md_file = os.path.join(output_folder, f"{filename}.md")

            # Open and process image
            with Image.open(jpg_file) as img:
                # Preprocess image for better OCR
                processed_image = preprocess_image(img)

                # OCR with better configuration for accuracy
                custom_config = r'--oem 3 --psm 6'
                text = pytesseract.image_to_string(
                    processed_image,
                    config=custom_config,
                    lang='eng'
                )

                # Clean and format text as markdown
                text = clean_text(text)

                # Write to markdown file
                with open(md_file, 'w', encoding='utf-8') as f:
                    f.write(text)

                print(f"Converted: {os.path.basename(jpg_file)} -> {filename}.md")
                converted.append(f"{filename}.md")

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
    print(convert_jpg_to_markdown())
