"""Convert R scripts (.R) to R Markdown (.Rmd).

For each .R file in input/, rewrites the source as an R Markdown document and writes
the .Rmd to output/.
"""

import os
import sys
from pathlib import Path

# Default folders live next to this script, so `python backend/R_Rmd.py` finds
# backend/input regardless of the shell's working directory.
SCRIPT_DIR = Path(__file__).resolve().parent


def convert_r_to_rmd(r_path: str, output_path: str | None = None,
                     input_dir: str | None = None, output_dir: str | None = None) -> bool:
    """Convert an R script to an R Markdown document.

    Args:
        r_path: Path to the .R file (relative to input folder or absolute)
        output_path: Desired output Rmd filename. If None, uses input stem + .Rmd
        input_dir: Input directory (default: the script's input/ folder)
        output_dir: Output directory (default: the script's output/ folder)

    Returns:
        bool: True if conversion successful, False otherwise
    """

    # Set default directories if not provided. Default relative to this script, not
    # the caller's working directory, so it works no matter where it's invoked from.
    script_dir = Path(__file__).resolve().parent

    if input_dir is None:
        input_dir = script_dir / "input"
    else:
        input_dir = Path(input_dir)

    if output_dir is None:
        output_dir = script_dir / "output"
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(exist_ok=True)
    
    # Check if already Rmd format
    try:
        if Path(r_path).suffix.lower() == ".rmd":
            print("That file is already in Rmd format")
            return False
    except Exception:
        pass
    
    # Build full input path
    full_input_path = Path(r_path) if os.path.isabs(str(r_path)) else input_dir / r_path
    if not full_input_path.exists():
        print(f"Error: R file '{full_input_path}' not found")
        return False
    
    # Compute output name
    if output_path is None:
        rmd_name = f"{full_input_path.stem}.Rmd"
    else:
        rmd_name = Path(output_path).name
        if not rmd_name.endswith('.Rmd') and not rmd_name.endswith('.rmd'):
            rmd_name += '.Rmd'
    full_output_path = output_dir / rmd_name
    
    try:
        # attempt to read R file
        with open(full_input_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        rmd_lines = []
        
        # Add YAML header
        rmd_lines.append("---\n")
        rmd_lines.append("title: \"R Analysis\"\n")
        rmd_lines.append("output: pdf_document\n")
        rmd_lines.append("---\n")
        rmd_lines.append("\n")
        
        # Track state
        in_code_chunk = False
        current_code = []
        consecutive_empty_lines = 0
        line_number = 0
        name_lines = []  # For collecting name/ID at the start
        last_added = None  # Track what we last added: 'code', 'comment', 'name', None
        max_empty_lines = 1  # Maximum consecutive empty lines to preserve
        
        def is_separator_line(text):
            """Check if line is just a separator (all = or -)"""
            text = text.strip()
            if not text:
                return False
            # Check if all characters are = or - or spaces
            return all(c in '=- ' for c in text) and ('=' in text or '-' in text)
        
        def flush_code_chunk():
            """Write accumulated code as an R code chunk"""
            nonlocal in_code_chunk, current_code
            if current_code:
                if not in_code_chunk:
                    rmd_lines.append("```{r}\n")
                    in_code_chunk = True
                for code_line in current_code:
                    rmd_lines.append(code_line)
                current_code = []
        
        def close_code_chunk():
            """Close the current R code chunk"""
            nonlocal in_code_chunk, last_added
            if in_code_chunk:
                rmd_lines.append("```\n")
                # Add one empty line after code chunk
                rmd_lines.append("\n")
                in_code_chunk = False
                last_added = 'code'
        
        def process_comment(comment_text, stripped_line):
            """Process a comment line and return markdown"""
            # Remove leading # and any extra spaces
            text = comment_text[1:].strip()
            
            # Check if it's a separator line (all = or -)
            if is_separator_line(text):
                # Skip separator lines
                return None
            
            # Check if it's a header (has multiple #)
            if stripped_line.startswith('##'):
                # Count # to determine header level
                hash_count = len(stripped_line) - len(stripped_line.lstrip('#'))
                header_text = stripped_line[hash_count:].strip()
                if header_text.startswith(' '):
                    header_text = header_text[1:]
                return f"{'#' * min(hash_count, 6)} {header_text}\n"
            elif 'ANALYSIS' in text.upper() or 'SECTION' in text.upper():
                # Likely a section header
                return f"## {text}\n"
            else:
                # Regular comment
                return f"{text}\n"
        
        # Process each line
        for line in lines:
            line_number += 1
            stripped = line.strip()
            original_line = line
            
            # Empty line
            if not stripped:
                consecutive_empty_lines += 1
                # Only add empty line if we're not in a code chunk
                if not in_code_chunk:
                    # Limit consecutive empty lines
                    if consecutive_empty_lines <= max_empty_lines:
                        rmd_lines.append("\n")
                elif consecutive_empty_lines >= 2:
                    # Multiple empty lines - close code chunk
                    flush_code_chunk()
                    close_code_chunk()
                    # Add one empty line after closing code chunk
                    if consecutive_empty_lines == 2:
                        rmd_lines.append("\n")
                    consecutive_empty_lines = 0
                continue
            
            consecutive_empty_lines = 0
            
            # Comment line (starts with #)
            if stripped.startswith('#'):
                # Close any open code chunk first
                flush_code_chunk()
                close_code_chunk()
                
                # Process the comment
                md_line = process_comment(stripped, stripped)
                
                if md_line is not None:
                    # Handle name/ID at the beginning (first few non-separator comments)
                    comment_text_after_hash = stripped[1:].strip()
                    if line_number <= 5 and not is_separator_line(comment_text_after_hash) and len(comment_text_after_hash) < 30:
                        name_lines.append(md_line.strip())
                    else:
                        # Write name lines if we have them, before this comment
                        if name_lines:
                            for nl in name_lines:
                                rmd_lines.append(f"**{nl}**  \n")
                            rmd_lines.append("\n")
                            name_lines = []
                            last_added = 'name'
                        
                        # Add comment
                        rmd_lines.append(md_line)
                        # Only add empty line if it's a header or if last wasn't a comment
                        is_header = md_line.startswith('#')
                        if is_header or last_added != 'comment':
                            rmd_lines.append("\n")
                        last_added = 'comment'
            else:
                # Code line
                # If we have name lines collected, write them now
                if name_lines:
                    # Format name/ID section
                    if len(name_lines) == 1:
                        rmd_lines.append(f"**{name_lines[0]}**\n\n")
                    else:
                        for nl in name_lines:
                            rmd_lines.append(f"**{nl}**  \n")
                        rmd_lines.append("\n")
                    name_lines = []
                    last_added = 'name'
                
                # Add to code chunk (will be grouped together)
                current_code.append(original_line)
        
        # Handle any remaining name lines
        if name_lines:
            if len(name_lines) == 1:
                rmd_lines.append(f"**{name_lines[0]}**\n\n")
            else:
                for nl in name_lines:
                    rmd_lines.append(f"**{nl}**  \n")
                rmd_lines.append("\n")
        
        # Flush any remaining content
        flush_code_chunk()
        close_code_chunk()
        
        # Post-process: collapse multiple consecutive empty lines into one
        cleaned_lines = []
        prev_was_empty = False
        for line in rmd_lines:
            if line == "\n":
                if not prev_was_empty:
                    cleaned_lines.append(line)
                prev_was_empty = True
            else:
                cleaned_lines.append(line)
                prev_was_empty = False
        
        rmd_lines = cleaned_lines
        
        # Clean up excessive empty lines at the end
        while rmd_lines and rmd_lines[-1] == "\n":
            rmd_lines.pop()
        # Add one final newline if file is not empty
        if rmd_lines:
            rmd_lines.append("\n")
        
        # Write Rmd file
        print(f"Converting '{full_input_path}' to '{full_output_path}'...")
        with open(full_output_path, 'w', encoding='utf-8') as f:
            f.writelines(rmd_lines)
        
        if full_output_path.exists():
            print(f"Successfully converted to '{full_output_path}'")
            return True
        else:
            print("Rmd file creation failed")
            return False
    
    except Exception as e:
        print(f"Error converting R to Rmd: {e}")
        return False


def main():
    parser = None
    try:
        import argparse
        parser = argparse.ArgumentParser(description="Convert R files to R Markdown")
        parser.add_argument("r_file", nargs="?", help="R file to convert (optional)")
        parser.add_argument("output_file", nargs="?", help="Output Rmd filename (optional)")
        parser.add_argument("--input-dir", default=SCRIPT_DIR / "input", help="Input directory (default: backend/input)")
        parser.add_argument("--output-dir", default=SCRIPT_DIR / "output", help="Output directory (default: backend/output)")
    except ImportError:
        pass
    
    if parser:
        args = parser.parse_args()
        input_dir = Path(args.input_dir)
        output_dir = Path(args.output_dir)
        output_dir.mkdir(exist_ok=True)
        
        if args.r_file:
            # Convert specific file
            success = convert_r_to_rmd(args.r_file, args.output_file, input_dir, output_dir)
            if not success:
                sys.exit(1)
        else:
            # Convert all .R files in input/
            r_files = sorted(p for p in input_dir.glob("*.R"))
            if not r_files:
                print(f"No .R files found in {input_dir} folder")
                print("Usage: python R_Rmd.py <file.R> [output.Rmd] [--input-dir DIR] [--output-dir DIR]")
                print("Example: python R_Rmd.py script.R")
                print("Example: python R_Rmd.py script.R output.Rmd")
                return
            any_failed = False
            for r_file in r_files:
                ok = convert_r_to_rmd(r_file.name, None, input_dir, output_dir)
                if not ok:
                    any_failed = True
            if any_failed:
                sys.exit(1)
    else:
        # Fallback to simple argument parsing
        if len(sys.argv) < 2:
            # No args: convert all .R files in input/ (resolved relative to this script)
            script_dir = Path(__file__).resolve().parent
            input_dir = script_dir / "input"
            output_dir = script_dir / "output"
            output_dir.mkdir(exist_ok=True)
            r_files = sorted(p for p in input_dir.glob("*.R"))
            if not r_files:
                print("No .R files found in input folder")
                print("Usage: python R_Rmd.py <file.R> [output.Rmd]")
                print("Example: python R_Rmd.py script.R")
                return
            any_failed = False
            for r_file in r_files:
                ok = convert_r_to_rmd(r_file.name, None, input_dir, output_dir)
                if not ok:
                    any_failed = True
            if any_failed:
                sys.exit(1)
            return
        
        r_file = sys.argv[1]
        output_file = sys.argv[2] if len(sys.argv) > 2 else None
        success = convert_r_to_rmd(r_file, output_file)
        if not success:
            sys.exit(1)


if __name__ == "__main__":
    main()

