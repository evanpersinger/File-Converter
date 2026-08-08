"""Combine multiple files into a single output file.

Reads files from input/, sorts them naturally (Q1, Q2, Q10), and merges by type:
images and PDFs are combined into one PDF, and text files are concatenated.
Writes the combined result to output/.
"""

import os
import sys
import re
from pathlib import Path



# test if user has correct packages installed
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from pypdf import PdfWriter, PdfReader
    HAS_PDF = True
except ImportError:
    try:
        from PyPDF2 import PdfFileWriter, PdfFileReader
        HAS_PDF = True
        PDF_LIB = 'pypdf2'
    except ImportError:
        HAS_PDF = False
        
        


def natural_sort_key(path):
    """Extract numbers from filename for natural sorting (Q1, Q2, Q10 instead of Q1, Q10, Q2)"""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', str(path.name))]


# Different spellings of one format, so combining IMG_1.jpg with IMG_2.jpeg is not
# rejected as a mix on a technicality.
SUFFIX_ALIASES = {'.jpeg': '.jpg', '.tif': '.tiff', '.htm': '.html'}


def canonical_suffix(path: Path) -> str:
    """Lowercased extension, with alternate spellings folded onto one name."""
    suffix = path.suffix.lower()
    return SUFFIX_ALIASES.get(suffix, suffix)


# setup file directories
# Resolved relative to this script, not the caller's working directory, so the
# folders are always backend/input and backend/output no matter where you run from.
def setup_directories():
    script_dir = Path(__file__).resolve().parent
    input_dir = script_dir / "input"
    output_dir = script_dir / "output"

    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)

    return input_dir, output_dir


def get_file_type(file_path: Path) -> str:
    """Detect file type from extension."""
    ext = file_path.suffix.lower()
    if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']:
        return 'image'
    elif ext == '.pdf':
        return 'pdf'
    else:
        return 'text'


def combine_files(file_paths: list[str], output_path: str | None = None) -> bool:
    input_dir, output_dir = setup_directories()
    
    if not file_paths:
        print("Error: No files specified to combine")
        return False
    
    # Build full input paths - always look in input folder unless absolute path is provided
    full_input_paths = []
    for file_path in file_paths:
        # If absolute path, use as-is; otherwise look in input folder
        if os.path.isabs(str(file_path)):
            full_path = Path(file_path)
        else:
            # Remove 'input/' or 'input\' prefix if user included it
            file_path_str = str(file_path)
            if file_path_str.startswith('input/'):
                file_path_clean = file_path_str[6:]  # Remove 'input/'
            elif file_path_str.startswith('input\\'):
                file_path_clean = file_path_str[6:]  # Remove 'input\\'
            else:
                file_path_clean = file_path_str
            full_path = input_dir / file_path_clean
        
        if not full_path.exists():
            print(f"Warning: File '{full_path}' not found in input folder, skipping")
            continue
        full_input_paths.append(full_path)
    
    if not full_input_paths:
        print("Error: No valid files found to combine")
        return False
    
    # Skip .DS_Store and other hidden/system files
    full_input_paths = [f for f in full_input_paths if not f.name.startswith('.')]
    
    if not full_input_paths:
        print("Error: No valid files found to combine")
        return False

    # Mixing formats used to write junk and report success: a .pdf among .txt files
    # landed in the text branch and its raw bytes went straight into the output. The
    # order of the list is left alone, files combine in the order they were passed.
    extensions = sorted({canonical_suffix(path) for path in full_input_paths})
    if len(extensions) > 1:
        print("Error: All files must have the same extension, got: "
              f"{', '.join(extensions)}")
        return False

    # Detect file types and group by type
    file_types = {}
    for file_path in full_input_paths:
        file_type = get_file_type(file_path)
        if file_type not in file_types:
            file_types[file_type] = []
        file_types[file_type].append(file_path)
    
    # Determine output format and name
    if output_path is None:
        # Auto-detect output format from input files
        if 'image' in file_types and len(file_types) == 1:
            # All images - use same format as first input file
            first_file_ext = file_types['image'][0].suffix.lower()
            output_name = f"combined{first_file_ext}"
            output_type = 'image'
        elif 'pdf' in file_types and len(file_types) == 1:
            # All PDFs - use same format as first input file
            first_file_ext = file_types['pdf'][0].suffix.lower()
            output_name = f"combined{first_file_ext}"
            output_type = 'pdf'
        else:
            # Mixed or text files - use same format as first input file
            first_file_ext = full_input_paths[0].suffix.lower() or '.txt'
            output_name = f"combined{first_file_ext}"
            output_type = 'text'
    else:
        # User specified output - determine type from extension
        output_name = Path(output_path).name
        output_type = get_file_type(Path(output_name))
    
    full_output_path = output_dir / output_name
    
    # Combine files based on detected type
    try:
        if output_type == 'image':
            # Combine images (vertically stacked)
            if 'image' not in file_types:
                print("Error: Cannot create image output from non-image files")
                return False
            
            if not HAS_PIL:
                print("Error: Pillow (PIL) is required to combine images. Install with: pip install pillow")
                return False
            
            images = []
            max_width = 0
            total_height = 0
            
            # Load all images
            for img_path in file_types['image']:
                img = Image.open(img_path)
                images.append(img)
                max_width = max(max_width, img.width)
                total_height += img.height
            
            # Create new image with combined dimensions
            combined = Image.new('RGB', (max_width, total_height), color='white')
            
            # Paste images vertically
            y_offset = 0
            for img in images:
                # Center image if narrower than max width
                x_offset = (max_width - img.width) // 2
                combined.paste(img, (x_offset, y_offset))
                y_offset += img.height
            
            # Save combined image
            combined.save(full_output_path)
            
        elif output_type == 'pdf':
            # Combine PDFs
            if 'pdf' not in file_types:
                print("Error: Cannot create PDF output from non-PDF files")
                return False
            
            if not HAS_PDF:
                print("Error: pypdf or PyPDF2 is required to combine PDFs. Install with: pip install pypdf")
                return False
            
            # Try using pypdf (newer)
            try:
                writer = PdfWriter()
                for pdf_path in file_types['pdf']:
                    reader = PdfReader(pdf_path)
                    for page in reader.pages:
                        writer.add_page(page)
                with open(full_output_path, 'wb') as outfile:
                    writer.write(outfile)
            except NameError:
                # Fall back to PyPDF2 (older)
                writer = PdfFileWriter()
                for pdf_path in file_types['pdf']:
                    reader = PdfFileReader(pdf_path)
                    for page_num in range(reader.numPages):
                        writer.addPage(reader.getPage(page_num))
                with open(full_output_path, 'wb') as outfile:
                    writer.write(outfile)
        
        else:
            # Combine text files
            with open(full_output_path, 'w', encoding='utf-8') as outfile:
                for i, input_path in enumerate(full_input_paths):
                    # Add separator between files (except before first file)
                    if i > 0:
                        outfile.write("\n" + "=" * 80 + "\n")
                        outfile.write(f"File: {input_path.name}\n")
                        outfile.write("=" * 80 + "\n\n")
                    
                    # Read and write file content
                    try:
                        with open(input_path, 'r', encoding='utf-8') as infile:
                            content = infile.read()
                            outfile.write(content)
                            # Add newline at end if file doesn't end with one
                            if content and not content.endswith('\n'):
                                outfile.write('\n')
                    except Exception as e:
                        print(f"Warning: Error reading '{input_path.name}': {e}")
                        continue
        
        if full_output_path.exists():
            print(f"Successfully combined {len(full_input_paths)} file(s) into '{full_output_path}'")
            return True
        else:
            print("Error: Output file was not created")
            return False
            
    except Exception as e:
        print(f"Error combining files: {e}")
        return False


def main():
    input_dir, output_dir = setup_directories()
    
    if len(sys.argv) < 2:
        # No args: combine all files in input/ folder (skip .DS_Store and other hidden files)
        all_files = sorted([f for f in input_dir.iterdir() if f.is_file() and not f.name.startswith('.')], 
                          key=natural_sort_key)
        if not all_files:
            print("No files found in input folder")
            print("Usage: python combine_files.py [file1] [file2] ... [output_file]")
            print("Example: python combine_files.py")
            print("         (combines all files in input/ folder - auto-detects output format)")
            print("Example: python combine_files.py file1.jpg file2.jpg")
            print("         (combines images into combined.jpg)")
            print("Example: python combine_files.py file1.pdf file2.pdf")
            print("         (combines PDFs into combined.pdf)")
            print("Example: python combine_files.py file1.txt file2.txt combined.txt")
            print("         (combines files with custom output name)")
            print("\nNote: Files are read from 'input/' folder and output is saved to 'output/' folder")
            print("      Output format matches input format (JPG→JPG, PDF→PDF, etc.)")
            return
        
        # Use all files, sorted alphabetically
        file_paths = [f.name for f in all_files]
        output_file = None
        print(f"Combining {len(file_paths)} file(s) from input folder...")
    else:
        # Has args: parse them
        args = sys.argv[1:]
        
        # If last arg looks like an output filename (has extension and no path separators),
        # treat it as output, otherwise all are input files
        if len(args) > 1:
            last_arg = args[-1]
            # Check if last arg looks like an output filename (has extension, no directory)
            if '.' in last_arg and '/' not in last_arg and '\\' not in last_arg:
                output_file = last_arg
                input_files = args[:-1]
            else:
                output_file = None
                input_files = args
        else:
            output_file = None
            input_files = args
        
        file_paths = input_files
    
    success = combine_files(file_paths, output_file)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
