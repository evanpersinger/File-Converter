# ss_txt.py
"""Screenshot -> text converter (OCR).

Two modes:
  - simple (default): OCR tuned for plain-text screenshots. Runs a few
    preprocessing passes and keeps the most complete result.
  - structured (--structured / --tables): OpenCV table detection, per-cell
    OCR, heavy OCR-error correction, and `| table |` formatting for images
    with tables or other structured layout.

English only: Tesseract is called with lang='eng', so text in another language comes
back as whatever English words its shapes resemble rather than as an error. The
error corrections in fix_common_ocr_errors assume English too, and the ones that
would rewrite ordinary words are limited to detected table cells.

Usage:
    python ss_txt.py               # plain text
    python ss_txt.py --structured  # tables / structured content
"""

import argparse
import os
import re
import sys
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}


# ---------------------------------------------------------------------------
# Shared cleanup
# ---------------------------------------------------------------------------
def join_continuation_lines(lines):
    """Join lines that clearly continue the same sentence.

    A line is joined onto the previous one when it starts lowercase, or when
    the previous line ends with continuation punctuation and the next doesn't
    start a new sentence. Blank lines and table lines (starting with '|') are
    treated as hard boundaries.
    """
    fixed_lines = []
    i = 0
    while i < len(lines):
        current_line = lines[i]

        # Preserve blank lines (paragraph breaks)
        if not current_line.strip():
            fixed_lines.append(current_line)
            i += 1
            continue

        # Leave table-formatted lines untouched
        if current_line.strip().startswith('|'):
            fixed_lines.append(current_line)
            i += 1
            continue

        # Pull in following lines that are clearly continuations
        while i + 1 < len(lines):
            next_line = lines[i + 1]

            # Stop at a paragraph break or a table line
            if not next_line.strip() or next_line.strip().startswith('|'):
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

    return fixed_lines


# ---------------------------------------------------------------------------
# Simple mode (plain-text screenshots)
# ---------------------------------------------------------------------------
def preprocess_image(image):
    """Produce several preprocessed variants of an image to improve OCR."""
    preprocessed_images = []

    # Enhanced grayscale
    gray_img = image.convert('L')
    gray_img = ImageEnhance.Contrast(gray_img).enhance(1.5)
    gray_img = ImageEnhance.Sharpness(gray_img).enhance(1.2)
    gray_img = gray_img.filter(ImageFilter.MedianFilter(size=3))
    preprocessed_images.append(gray_img)

    # High-contrast grayscale for colored backgrounds
    gray_high = image.convert('L')
    gray_high = ImageEnhance.Contrast(gray_high).enhance(2.5)
    preprocessed_images.append(gray_high)

    # Original color (better for colored text/backgrounds). Always convert to a
    # fresh copy, even if already RGB: passing the source image straight to
    # tesseract can raise "Unsupported image format/type" because of its
    # lingering JPEG format/filename metadata. convert() drops that.
    color_img = image.convert('RGB')
    preprocessed_images.append(color_img)

    return preprocessed_images


def clean_text(text):
    """Clean plain OCR text: trim whitespace and rejoin split sentences."""
    if not text:
        return ""

    text = re.sub(r'\n{3,}', '\n\n', text)
    lines = [line.rstrip() for line in text.split('\n')]
    lines = join_continuation_lines(lines)
    text = '\n'.join(lines)

    text = re.sub(r' +', ' ', text)
    text = re.sub(r'\n +', '\n', text)  # remove leading spaces after newlines
    return text.strip()


def convert_simple(image_path):
    """Convert a plain-text screenshot to text using multiple preprocessing passes."""
    try:
        image = Image.open(image_path)
        processed_images = preprocess_image(image)

        custom_config = r'--oem 3 --psm 6'
        all_texts = []
        for processed_image in processed_images:
            # Wrap each pass so one failing variant can't sink the whole result
            try:
                text = pytesseract.image_to_string(processed_image, config=custom_config, lang='eng')
            except Exception as ocr_error:
                print(f"  OCR pass skipped: {ocr_error}")
                continue
            if text and text.strip():
                all_texts.append(text)

        # Keep the longest result (likely the most complete)
        text = max(all_texts, key=len) if all_texts else ""
        return clean_text(text)

    except Exception as e:
        print(f"Error processing image: {e}")
        return None


# ---------------------------------------------------------------------------
# Structured mode (tables / structured content)
# ---------------------------------------------------------------------------
def detect_table_structure(image):
    """Detect table structure and extract cell regions.

    Uses line detection (for bordered tables) and, as a fallback, connected
    components (for borderless, aligned-text tables). Returns an enhanced
    grayscale image plus a list of (x, y, w, h) cell regions.
    """
    img_array = np.array(image)

    if len(img_array.shape) == 3:
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    else:
        gray = img_array

    # Scale up small images for better detection
    original_height, original_width = gray.shape
    scale = 1.0
    if original_width < 1000:
        scale = 2.0
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    height, width = gray.shape

    # Binarize with two methods and combine
    binary1 = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 11, 2
    )
    _, binary2 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    binary = cv2.bitwise_or(binary1, binary2)

    # METHOD 1: bordered tables via horizontal/vertical line detection
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(int(width * 0.1), 20), 1))
    detected_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
    horizontal_lines = cv2.dilate(detected_lines, horizontal_kernel, iterations=2)

    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(int(height * 0.1), 20)))
    detected_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
    vertical_lines = cv2.dilate(detected_lines, vertical_kernel, iterations=2)

    table_mask = cv2.addWeighted(horizontal_lines, 0.5, vertical_lines, 0.5, 0.0)
    contours, _ = cv2.findContours(table_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    table_cells = []
    min_area = (width * height) * 0.001
    for contour in contours:
        area = cv2.contourArea(contour)
        if area > min_area:
            x, y, w, h = cv2.boundingRect(contour)
            if w > 20 and h > 20 and w < width * 0.9 and h < height * 0.9:
                table_cells.append((x, y, w, h))

    # METHOD 2: borderless tables via connected components (only if lines found little)
    if len(table_cells) < 2:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        dilated = cv2.dilate(binary, kernel, iterations=1)
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(dilated, connectivity=8)

        text_regions = []
        for i in range(1, num_labels):  # skip background (label 0)
            x, y, w, h, area = stats[i]
            if (w > 15 and h > 10 and w < width * 0.3 and h < height * 0.2 and
                    area > 50 and area < width * height * 0.1):
                text_regions.append((x, y, w, h))

        # Validate that the regions actually form a table
        if len(text_regions) >= 4:
            sorted_regions = sorted(text_regions, key=lambda r: r[1])
            avg_height = sum(h for _, _, _, h in text_regions) / len(text_regions)
            row_tolerance = max(avg_height * 0.6, 20)

            rows = []
            current_row = []
            last_y = sorted_regions[0][1]
            for region in sorted_regions:
                _, y, _, _ = region
                if abs(y - last_y) <= row_tolerance:
                    current_row.append(region)
                else:
                    if current_row:
                        rows.append(current_row)
                    current_row = [region]
                    last_y = y
            if current_row:
                rows.append(current_row)

            if len(rows) >= 2:
                cols_per_row = [len(row) for row in rows]
                avg_cols = sum(cols_per_row) / len(cols_per_row)
                similar_cols = sum(1 for c in cols_per_row if abs(c - avg_cols) <= 1)
                if similar_cols >= len(rows) * 0.7:
                    for row in rows:
                        row.sort(key=lambda r: r[0])
                    num_cols = int(round(avg_cols))
                    if num_cols >= 2:
                        first_row_x = [r[0] for r in rows[0]] if len(rows[0]) >= num_cols else []
                        if first_row_x:
                            aligned_rows = 1
                            x_tolerance = width * 0.15
                            for row in rows[1:]:
                                if len(row) >= num_cols:
                                    row_aligned = True
                                    for i in range(min(len(row), len(first_row_x))):
                                        if abs(row[i][0] - first_row_x[i]) > x_tolerance:
                                            row_aligned = False
                                            break
                                    if row_aligned:
                                        aligned_rows += 1
                            if aligned_rows >= len(rows) * 0.6:
                                table_cells = text_regions

    # Enhance the image for OCR: denoise -> CLAHE contrast -> sharpen
    denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)
    kernel = np.array([[-1, -1, -1],
                       [-1, 9, -1],
                       [-1, -1, -1]])
    sharpened = cv2.filter2D(enhanced, -1, kernel)

    # Scale coordinates/image back down if we scaled up
    if scale > 1.0:
        sharpened = cv2.resize(sharpened, (original_width, original_height), interpolation=cv2.INTER_AREA)
        table_cells = [(int(x / scale), int(y / scale), int(w / scale), int(h / scale))
                       for x, y, w, h in table_cells]

    return Image.fromarray(sharpened), table_cells


def are_texts_similar(text1, text2, threshold=0.7):
    """Return True if two texts are similar (used to dedupe OCR results)."""
    if not text1 or not text2:
        return False

    def normalize(t):
        return re.sub(r'\s+', ' ', t.lower().strip())

    norm1 = normalize(text1)
    norm2 = normalize(text2)

    shorter, longer = (norm1, norm2) if len(norm1) < len(norm2) else (norm2, norm1)
    if len(shorter) > 0:
        similarity = len(shorter) / len(longer) if len(longer) > 0 else 0
        if similarity >= threshold:
            return True

    words1 = set(norm1.split())
    words2 = set(norm2.split())
    if len(words1) == 0 or len(words2) == 0:
        return False

    overlap = len(words1 & words2)
    total_unique = len(words1 | words2)
    similarity = overlap / total_unique if total_unique > 0 else 0
    return similarity >= threshold


def fix_common_ocr_errors(text, table_cells=False):
    """Fix common OCR misreadings (bubbles, l/1/I confusion, etc.).

    Args:
        table_cells: True only when `text` came out of a detected table cell. Some
            corrections are safe there and destructive anywhere else, so they are off
            by default and a caller has to opt in.
    """
    if not text:
        return text

    # Remove empty circles / MCQ bubbles (© symbol)
    text = re.sub(r'©\s*(\d+)', r'\1', text)   # "©2" -> "2"
    text = re.sub(r'©\s*\)', ')', text)         # "©)" -> ")"
    text = re.sub(r'©\s*', '', text)
    text = re.sub(r'©', '', text)

    # Single-letter misreadings with leading "I"/"l"
    for bad, good in (('Ic', 'c'), ('Ia', 'a'), ('Ib', 'b'), ('la', 'a'), ('lc', 'c'), ('lb', 'b')):
        text = re.sub(rf'\b{bad}\b', good, text)

    # Same fixes at start of line or surrounded by spaces
    for bad, good in (('Ia', 'a'), ('Ic', 'c'), ('Ib', 'b'), ('la', 'a'), ('lc', 'c'), ('lb', 'b')):
        text = re.sub(rf'^{bad}\s', f'{good} ', text)
        text = re.sub(rf'\s{bad}\s', f' {good} ', text)

    # Table header patterns
    if table_cells:
        text = re.sub(r'\bIa\s+b\s+Ic\b', 'a b c', text)
        text = re.sub(r'\bla\s+b\s+lc\b', 'a b c', text)
        text = re.sub(r'^Ia\s+b\s+Ic\s*$', 'a b c', text, flags=re.MULTILINE)
        text = re.sub(r'^la\s+b\s+lc\s*$', 'a b c', text, flags=re.MULTILINE)

    # Empty circle artifacts
    text = re.sub(r'\bOo\b', '', text)
    text = re.sub(r'^Oo\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\bOs(\d+)\b', r'\1', text)  # "Os6" -> "6"

    # letter + "1" misread as letter + "i"/"l"/"t". Cell text only: a two-character
    # cell holds a label like a1 or b1 and the trailing character is a misread 1, but
    # the same patterns match ordinary short words, so running them over a paragraph
    # turns "at" into "a1", "it" into "i1" and "hi" into "h1".
    if table_cells:
        text = re.sub(r'\b([a-z])i\b', r'\g<1>1', text)  # "bi" -> "b1"
        text = re.sub(r'\b([a-z])l\b', r'\g<1>1', text)  # "al" -> "a1"
        text = re.sub(r'\blon\b', 'c1', text)            # "lon" -> "c1"
        text = re.sub(r'\b1t\b', 'a1', text)             # "1t" -> "a1"
        text = re.sub(r'\bat\b', 'a1', text)             # "at" -> "a1"
        text = re.sub(r'\b([a-z])t\b', r'\g<1>1', text)  # "bt" -> "b1"

    # Number misreadings (l0 -> 0, O1 -> 1, I0 -> 10, ...)
    corrections = {
        **{rf'\bl{d}\b': str(d) for d in range(10)},
        **{rf'\bO{d}\b': str(d) for d in range(10)},
        r'\bI0\b': '10',
        r'\bI1\b': '11',
    }
    for pattern, replacement in corrections.items():
        text = re.sub(pattern, replacement, text)

    # Drop artifact-only lines (single stray chars), keep valid single alphanumerics
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if len(stripped) > 1 or (len(stripped) == 1 and stripped.isalnum()):
            cleaned_lines.append(line)
        elif not stripped and cleaned_lines and cleaned_lines[-1].strip():
            cleaned_lines.append(line)
    return '\n'.join(cleaned_lines).strip()


def preprocess_cell_image(cell_img):
    """Preprocess an individual table-cell image for better OCR."""
    height, width = cell_img.shape[:2]
    if width < 50 or height < 20:
        scale = max(50 / width, 20 / height, 2.0)
        cell_img = cv2.resize(cell_img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    denoised = cv2.fastNlMeansDenoising(cell_img, None, 10, 7, 21)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)
    kernel = np.array([[-1, -1, -1],
                       [-1, 9, -1],
                       [-1, -1, -1]])
    sharpened = cv2.filter2D(enhanced, -1, kernel)
    return Image.fromarray(sharpened)


def group_cells_into_rows(table_cells, row_tolerance=None):
    """Group (x, y, w, h) cells into rows by their y-coordinate."""
    if not table_cells:
        return []

    if row_tolerance is None:
        avg_height = sum(h for _, _, _, h in table_cells) / len(table_cells)
        row_tolerance = max(avg_height * 0.5, 15)

    sorted_cells = sorted(table_cells, key=lambda cell: (cell[1], cell[0]))

    rows = []
    current_row = []
    current_row_y = None
    for cell in sorted_cells:
        x, y, w, h = cell
        cell_center_y = y + h // 2

        if current_row_y is None or abs(cell_center_y - current_row_y) <= row_tolerance:
            current_row.append(cell)
            if current_row_y is None:
                current_row_y = cell_center_y
            else:
                current_row_y = sum(cy + ch // 2 for _, cy, _, ch in current_row) / len(current_row)
        else:
            if current_row:
                current_row.sort(key=lambda c: c[0])
                rows.append(current_row)
            current_row = [cell]
            current_row_y = cell_center_y

    if current_row:
        current_row.sort(key=lambda c: c[0])
        rows.append(current_row)

    return rows


def extract_table_cells(image, table_cells):
    """Extract text from individual table cells and format as pipe-delimited rows."""
    if not table_cells:
        return ""

    img_array = np.array(image)
    if len(img_array.shape) == 3:
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    else:
        gray = img_array

    rows = group_cells_into_rows(table_cells)
    if not rows:
        return ""

    cell_texts = []
    for row_cells in rows:
        row_texts = []
        for x, y, w, h in row_cells:
            padding = 5
            y1 = max(0, y - padding)
            x1 = max(0, x - padding)
            y2 = min(gray.shape[0], y + h + padding)
            x2 = min(gray.shape[1], x + w + padding)

            cell_img = gray[y1:y2, x1:x2]
            if cell_img.size < 100:
                continue

            cell_pil = preprocess_cell_image(cell_img)

            # Try several PSM modes and keep the best
            cell_texts_tried = []
            for psm in [7, 8, 6, 11]:  # line, word, block, sparse
                try:
                    config = f'--oem 3 --psm {psm}'
                    text = pytesseract.image_to_string(cell_pil, config=config, lang='eng').strip()
                    if text:
                        cell_texts_tried.append(fix_common_ocr_errors(text, table_cells=True))
                except Exception:
                    continue

            if cell_texts_tried:
                text = fix_common_ocr_errors(
                    max(cell_texts_tried, key=len).strip(), table_cells=True
                )
                if text:
                    row_texts.append(text)

        if row_texts:
            cell_texts.append('| ' + ' | '.join(row_texts) + ' |')

    return '\n'.join(cell_texts)


def extract_with_multiple_psm_modes(image):
    """Run OCR with several PSM modes and return the best unique result."""
    psm_modes = [
        (6, "Uniform block"),   # best for tables
        (11, "Sparse text"),
        (4, "Single column"),
        (3, "Automatic"),       # fallback
    ]

    results = []
    for psm, description in psm_modes:
        try:
            config = f'--oem 3 --psm {psm}'
            text = pytesseract.image_to_string(image, config=config, lang='eng').strip()
            if text and len(text) > 10:
                text = fix_common_ocr_errors(text)
                results.append({'text': text, 'psm': psm, 'description': description, 'length': len(text)})
        except Exception:
            continue

    if not results:
        return ""

    # Deduplicate, preferring the longer of similar results
    unique_results = []
    for result in results:
        is_duplicate = False
        for existing in unique_results:
            if are_texts_similar(result['text'], existing['text']):
                if result['length'] > existing['length']:
                    unique_results.remove(existing)
                    unique_results.append(result)
                is_duplicate = True
                break
        if not is_duplicate:
            unique_results.append(result)

    if unique_results:
        return max(unique_results, key=lambda x: x['length'])['text']
    return ""


def detect_and_group_table_lines(lines):
    """Group runs of short single-token lines into pipe-delimited table rows."""
    if not lines:
        return lines

    table_cell_indices = []
    table_cells = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and len(stripped) <= 8 and ' ' not in stripped:
            table_cell_indices.append(i)
            table_cells.append(stripped)

    if len(table_cells) < 4:
        return lines

    # Pick the column count that fits best (prefer 3)
    best_column_count = 3
    best_fit_score = -1000
    for col_count in [3, 2, 4]:
        complete_rows = len(table_cells) // col_count
        remainder = len(table_cells) % col_count
        if remainder == 0:
            fit_score = complete_rows * 100 + (10 if col_count == 3 else 0)
        else:
            fit_score = complete_rows * 10 - remainder * 5
        if fit_score > best_fit_score:
            best_fit_score = fit_score
            best_column_count = col_count

    table_rows = []
    for i in range(0, len(table_cells), best_column_count):
        row_cells = table_cells[i:i + best_column_count]
        if len(row_cells) >= 2:
            table_rows.append('| ' + ' | '.join(row_cells) + ' |')

    # Replace the table section with the grouped rows
    result = []
    i = 0
    processed_indices = set()
    while i < len(lines):
        if i in table_cell_indices and i not in processed_indices:
            j = i
            while j < len(lines):
                if j in table_cell_indices:
                    processed_indices.add(j)
                    j += 1
                elif not lines[j].strip() and j + 1 < len(lines) and (j + 1) in table_cell_indices:
                    j += 1
                else:
                    break
            for row in table_rows:
                result.append(row)
            i = j
        else:
            if i not in processed_indices:
                result.append(lines[i])
            i += 1

    return result


def clean_structured_text(text, is_table=False):
    """Clean and format extracted structured text."""
    if not text:
        return ""

    text = fix_common_ocr_errors(text, table_cells=is_table)
    text = re.sub(r'\n{3,}', '\n\n', text)
    lines = [line.rstrip() for line in text.split('\n')]

    # Rejoin split sentences for non-table text
    if not is_table:
        lines = join_continuation_lines(lines)

    text = '\n'.join(lines)

    if not is_table:
        # Detect cell-per-line tables and space/tab-aligned table rows
        lines = detect_and_group_table_lines(text.split('\n'))
        formatted_lines = []
        for line in lines:
            if re.search(r'\s{3,}', line) or '\t' in line:
                parts = [p.strip() for p in re.split(r'\s{2,}|\t+', line) if p.strip()]
                if (2 <= len(parts) <= 6 and
                        all(len(part) < 50 for part in parts) and
                        not any(len(part) > 30 and ' ' in part for part in parts)):
                    formatted_lines.append('| ' + ' | '.join(parts) + ' |')
                else:
                    formatted_lines.append(line)
            else:
                formatted_lines.append(line)
        text = '\n'.join(formatted_lines)

    text = re.sub(r' +', ' ', text)
    text = re.sub(r'\n +', '\n', text)
    return text.strip()


def convert_structured(image_path):
    """Convert an image with tables/structured content to formatted text."""
    try:
        image = Image.open(image_path)
        processed_image, table_cells = detect_table_structure(image)

        # Extract from detected cells first
        table_text = ""
        if table_cells and len(table_cells) >= 2:
            table_text = extract_table_cells(image, table_cells)

        # Regular OCR as well (captures surrounding text / no-table case)
        regular_text = extract_with_multiple_psm_modes(processed_image)

        if table_text and len(table_text.strip()) > 0:
            text = table_text
            # Prepend non-table content (e.g. a question above the table)
            if regular_text and not are_texts_similar(table_text, regular_text, threshold=0.3):
                regular_lines = [line.strip() for line in regular_text.split('\n') if line.strip()]
                table_lines = [line.strip() for line in table_text.split('\n') if line.strip()]
                unique_regular = [line for line in regular_lines
                                  if not any(are_texts_similar(line, t_line, 0.5) for t_line in table_lines)]
                if unique_regular:
                    text = '\n'.join(unique_regular) + "\n\n" + table_text
            text = clean_structured_text(text, is_table=True)
        else:
            text = clean_structured_text(regular_text, is_table=False)

        return text

    except Exception as e:
        print(f"Error processing image: {e}")
        import traceback
        traceback.print_exc()
        return None


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def find_images(input_folder):
    return sorted(f for f in os.listdir(input_folder)
                  if Path(f).suffix.lower() in IMAGE_EXTENSIONS)


def convert_screenshots_to_text(structured: bool = False) -> str:
    """Convert every screenshot/image in the input folder to text using OCR.

    All extracted text is combined into a single .txt file in the output folder.

    Args:
        structured: If True, use table/layout-aware extraction (slower, better for
            tables and complex layouts). If False, use plain-text extraction.

    Returns:
        A summary of what was converted, suitable for showing to a caller.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_folder = os.path.join(script_dir, "input")
    output_folder = os.path.join(script_dir, "output")

    if not os.path.exists(input_folder):
        return f"Error: '{input_folder}' folder not found"
    os.makedirs(output_folder, exist_ok=True)

    image_files = find_images(input_folder)
    if not image_files:
        if any(f.lower().endswith('.txt') for f in os.listdir(input_folder)):
            return "That file is already in txt format"
        return (f"No image files found in '{input_folder}' folder. "
                "Supported formats: PNG, JPG, JPEG, GIF, BMP, TIFF, WEBP")

    if structured:
        mode, convert = "structured", convert_structured
        combined_filename = "all_extracted_structured_text.txt"
    else:
        mode, convert = "simple", convert_simple
        combined_filename = "all_extracted_text_combined.txt"
    combined_path = os.path.join(output_folder, combined_filename)

    print(f"Found {len(image_files)} image(s) to process ({mode} mode):")
    for img in image_files:
        print(f"  - {img}")
    print("\nProcessing...")

    all_text_parts = []
    failed = []
    for image_filename in image_files:
        image_path = os.path.join(input_folder, image_filename)
        print(f"\nConverting: {image_filename}")
        text = convert(image_path)
        if text:
            all_text_parts.append(text)
            print("Success")
        else:
            print(f"Failed: {image_filename}")
            failed.append(image_filename)

    if not all_text_parts:
        print("\nNo text extracted from any images")
        return f"No text extracted from any of the {len(image_files)} image(s)"

    with open(combined_path, 'w', encoding='utf-8') as f:
        f.write('\n\n'.join(all_text_parts))
    print(f"\nAll text saved to: {combined_filename}")

    summary = (f"Extracted text from {len(all_text_parts)} image(s) ({mode} mode) "
               f"into output/{combined_filename}")
    if failed:
        summary += f". {len(failed)} failed: {', '.join(failed)}"
    return summary


def main():
    parser = argparse.ArgumentParser(description="Convert screenshots/images to text using OCR.")
    parser.add_argument(
        "--structured", "--tables", dest="structured", action="store_true",
        help="Use table/structure-aware extraction (default: plain text).",
    )
    args = parser.parse_args()

    result = convert_screenshots_to_text(structured=args.structured)
    print(f"\n{result}")

    # Non-zero exit when nothing came out, so shell callers can tell
    if result.startswith(("Error:", "No ")):
        sys.exit(1)


if __name__ == "__main__":
    main()
