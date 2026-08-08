# File Converter

Simple scripts to convert files between different formats. Includes a local web UI and
an AI agent for interactive file conversion.

## Quick Start

### Web UI

Upload a file, pick a target format, download the result. Two terminals, both run from
the project root:

```bash
# Terminal 1: frontend
cd frontend && pnpm install && pnpm dev

# Terminal 2: backend
uv run uvicorn server:app --app-dir backend --reload --port 8000 --loop asyncio
```

Open **http://localhost:5173**. Both have to be running.

`--app-dir backend` and `--loop asyncio` are both required, the backend won't start
without them.

### AI Agent (Interactive Conversion)
Use the AI agent to convert files through natural language:

```bash
# After installation, you can use the command directly:
file-convert-agent

# Or run the script directly:
python backend/agent.py
```

Then ask it to convert files:
- "Convert mock1.md to PDF"
- "What files are in the input folder?"
- "Convert all Word documents to PDF"

The agent can use all conversion functions directly.

### Individual Scripts
Each script can be run independently for specific conversions (see details below).

## Scripts

### agent.py
AI-powered file conversion agent that can convert files through natural language interaction.

**Usage:**
```bash
# Using the installed command:
file-convert-agent

# Or run directly:
python backend/agent.py
```

**Python packages:**
- openai-agents>=0.5.0
- openai>=2.7.1

**API Key Requirements:**
- Currently supports **OpenAI API keys only**
- The agent uses the `openai-agents` package which is built specifically for OpenAI's API
- Set your API key in environment variables: `export OPENAI_API_KEY=your_api_key_here`
- Or add it to your `.env` file: `OPENAI_API_KEY=your_api_key_here`
- Note: OpenAI-compatible APIs may work but are not officially tested

**Features:**
- Interactive conversation interface
- Natural language file conversion requests
- Direct access to every conversion script in this repo
- Can list the input/output folders and read files
- Web search capability for additional information

**Example interactions:**
- "Convert mock1.md to PDF"
- "List all files in the input folder"
- "What conversions are supported?"

**Tools available to the agent:**

File tools: `list_files` (list the input or output folder), `read_file`, web search.

Batch converters take no arguments. Each converts every matching file in `input/` and
returns a summary of what it did:

`convert_csv_to_markdown`, `convert_csv_to_xlsx`, `convert_xlsx_to_csv`,
`convert_pdf_to_markdown`, `convert_pdf_to_markdown_openai`, `convert_pptx_to_markdown`,
`convert_pptx_to_pdf`, `convert_heic_to_jpg`, `convert_heic_to_markdown`,
`convert_jpg_to_markdown`, `convert_jpg_to_pdf`, `convert_jpg_to_ocr`,
`convert_png_to_pdf`, `convert_sql_files`, `convert_screenshots_to_text`

Single-file converters take a filename from `input/` plus an optional output name:

`convert_md_to_pdf`, `convert_docx_to_pdf`, `convert_txt_to_pdf`, `convert_html_to_pdf`,
`convert_notebook_to_pdf`, `convert_r_to_rmd`, `convert_rmd_to_pdf`, `combine_files`

**Note on script structure:** every conversion script keeps its logic in a named
function behind an `if __name__ == "__main__":` guard, so importing a script never
runs a conversion as a side effect. Keep that pattern when adding new converters,
otherwise the agent can't import them safely.

### xlsx_csv.py
Converts Excel (.xlsx) to CSV (.csv).

**Usage:**
```bash
python backend/xlsx_csv.py
```

**Python packages:**
- pandas>=2.2.3

**How it works:**
1. Automatically processes ALL XLSX files in the `input/` folder
2. Converts Excel files to CSV format
3. Saves CSV files to the `output/` folder

### csv_xlsx.py
Converts CSV (.csv) to Excel (.xlsx).

**Usage:**
```bash
python backend/csv_xlsx.py
```

**Python packages:**
- pandas>=2.2.3
- openpyxl>=3.1.5

**How it works:**
1. Automatically processes ALL CSV files in the `input/` folder
2. Converts CSV files to Excel format
3. Saves XLSX files to the `output/` folder

### csv_md.py
Converts CSV (.csv) files to Markdown (.md) tables.

**Usage:**
```bash
python backend/csv_md.py
```

**Python packages:**
- None beyond the standard library

**How it works:**
1. Automatically processes ALL CSV files in the `input/` folder
2. Converts each CSV into a Markdown table with a header row and separator row
3. Saves markdown files to the `output/` folder

### pdf_md.py
Converts PDF files to Markdown. Searchable pages become real Markdown (headings, lists, tables, code) via pymupdf4llm; scanned/image pages fall back to Tesseract OCR, handled page by page so mixed PDFs work. Math notation (LaTeX `\( \)` / `$$`, super/subscripts, operators) is normalized.

**Usage:**
```bash
python backend/pdf_md.py
```

**Python packages:**
- pymupdf4llm>=0.0.17
- pymupdf>=1.26.4
- pytesseract>=0.3.13
- pillow>=11.3.0

**System requirements (for OCR on scanned PDFs):**
- Tesseract OCR (macOS: `brew install tesseract`)

### openai_pdf_md.py
Converts PDF files to Markdown using OpenAI's Vision API for high-quality conversion.

**Usage:**
```bash
python backend/openai_pdf_md.py
```

**Python packages:**
- vision-parse>=0.1.13
- python-dotenv>=1.1.1
- openai>=2.7.1 (installed as dependency)

**Configuration:**
1. Create a `.env` file in the project root
2. Add your OpenAI API key: `OPENAI_API_KEY=your_api_key_here`

**Setup:**
All dependencies are installed automatically when you run `uv sync`

**Important Note:**
Combining several images into one large image before converting to PDF makes this script
very slow and can make it fail. See [CONVERSIONS.md](CONVERSIONS.md) for why, and what to
do instead.

### ss_txt.py
Converts screenshots and images to text using OCR (Optical Character Recognition). Has two modes: plain text (default) and structured content (tables/layout).

**Usage:**
```bash
python backend/ss_txt.py               # simple mode: plain-text screenshots
python backend/ss_txt.py --structured  # structured mode: tables / complex layout
```

**Python packages:**
- pytesseract>=0.3.13
- pillow>=11.3.0
- opencv-python>=4.12.0.88
- numpy>=2.2.5

**System requirements:**
- Tesseract OCR (macOS: `brew install tesseract`)

**Setup:**
```bash
# Install Tesseract OCR on macOS
brew install tesseract

# Python packages are installed via pyproject.toml
uv sync
```

**Supported formats:**
- PNG, JPG, JPEG, GIF, BMP, TIFF, WEBP

**How it works:**
1. Automatically processes ALL images in the `input/` folder
2. Preprocesses images for better OCR accuracy
3. Extracts text using OCR with proper sentence structure
4. Fixes random line breaks and preserves sentence flow

**Simple mode (default):**
- Image preprocessing for better accuracy
- Sentence structure preservation and line-break fixing
- Saves combined text to `output/all_extracted_text_combined.txt`

**Structured mode (`--structured` / `--tables`):**
- OpenCV table detection (bordered and borderless) and per-cell OCR
- Heavy OCR-error correction, formats tables with `|` separators
- Better handling of complex layouts
- Saves to `output/all_extracted_structured_text.txt`

### ipynb_pdf.py
Converts Jupyter notebooks (.ipynb) to PDF files.

**Usage:**
```bash
# Option A: run with no args – auto-detect a single notebook in input/
python backend/ipynb_pdf.py

# Option B: specify a file (filename only; script prepends input/)
python backend/ipynb_pdf.py notebook_name.ipynb
python backend/ipynb_pdf.py notebook_name.ipynb custom_output.pdf
```

**Python packages:**
- jupyter>=1.1.1
- nbconvert>=7.16.6
- nbclient>=0.10.2
- nbformat>=5.10.4
- jinja2>=3.1.6
- traitlets>=5.14.3

**System requirements:**
- LaTeX distribution for PDF export (macOS: `brew install --cask mactex`)

**Setup:**
```bash
# Python packages installed via pyproject.toml
uv sync

# Install LaTeX on macOS
brew install --cask mactex
```

**How it works:**
1. Put your `.ipynb` file in the `input/` folder
2. If you run without arguments and there is exactly one notebook in `input/`,
   the script prints only the file name (e.g., `HW2.ipynb`) and converts it.
3. If multiple notebooks are present, it lists them and asks you to specify one.
4. If none are present, it shows usage instructions.
5. PDF is saved to the `output/` folder. Custom output filenames are supported.

**Alternative (no LaTeX):**
If you prefer not to install LaTeX, you can export using the browser-based PDF:
```bash
pip install pyppeteer
jupyter nbconvert --to webpdf --output output/NAME.pdf input/NAME.ipynb
```

### md_pdf.py
Converts Markdown (.md) files to PDF using Pandoc with enhanced math symbol and formatting support.

**Usage:**
```bash
# Convert all .md files in input/ folder
python backend/md_pdf.py

# Convert specific file
python backend/md_pdf.py file.md [output.pdf]
```

**Python packages:**
- nbconvert>=7.16.6 (only for pandocfilters; not strictly required to run pandoc)
- pandocfilters>=1.5.1 (installed, but conversion is done by the pandoc CLI)

**System requirements:**
- Pandoc (macOS: `brew install pandoc`)
- LaTeX engine (XeLaTeX recommended) for PDF generation (macOS: `brew install --cask mactex`)
- mermaid-filter for Mermaid diagram support (requires Node.js/pnpm):
  ```bash
  pnpm add -g mermaid-filter
  ```

**Features:**
- **Mermaid diagrams**: Renders directed/undirected graphs, flowcharts, and more using Mermaid syntax:
  ````
  ```mermaid
  graph LR
      a -->|3| b
      b -->|5| c
  ```
  ````
  Supported layout directions: `LR` (left-right), `TD` (top-down), `RL`, `BT`
- **ASCII art diagrams**: Automatically detects and preserves ASCII graph diagrams (arrows like `-->`, `<--`, pipe characters) in a monospace block so spacing is not lost
- **Unicode math symbols**: Properly renders Unicode symbols in math mode:
  - Greek letters: ε (epsilon), α (alpha), β (beta), γ (gamma), δ (delta), θ (theta), λ (lambda), μ (mu), σ (sigma), ρ (rho), τ (tau), π (pi)
  - Comparison operators: ≤ (less than or equal), ≥ (greater than or equal)
  - Other symbols: ± (plus-minus), ≈ (approximately equal)
  - Set theory: ∪ (union), ∩ (intersection), ∈ (element of), ∃ (exists), ∀ (for all), ⋈ (bowtie)
- **Unicode subscripts**: Converts Unicode subscripts (₀, ₁, ₂, etc.) to LaTeX subscripts:
  - `θ₀` → `$\theta_0$`, `x₁` → `$x_1$`, `θₙ` → `$\theta_n$`
- **LaTeX math commands**: Converts complex symbols to LaTeX commands:
  - ∑ (sum), ∫ (integral), ∞ (infinity), ≠ (not equal)
- **Math expression combination**: Automatically combines adjacent math expressions in table cells:
  - `$d_i$ = $y_i$ - $x_i$` → `$d_i = y_i - x_i$`
- **Table page break prevention**: Tables automatically move to the next page if they don't fit, preventing tables from splitting across pages
- **Horizontal rules**: Converts `---` to proper spacing/breaks
- **Inline math mode**: Keeps math symbols on the same line as text
- **Font support**: Uses fontspec and amssymb for proper Unicode and LaTeX symbol rendering
- **Display math**: Supports both `$$...$$` and `\[...\]` for display math blocks

### html_pdf.py
Converts HTML files to PDF. Prefers `wkhtmltopdf`; falls back to `pandoc` if unavailable.

**Usage:**
```bash
python backend/html_pdf.py file.html [output.pdf]
```

**Python packages:**
- None beyond the standard library

**System requirements:**
- wkhtmltopdf (recommended for best HTML rendering) — macOS: `brew install wkhtmltopdf`
- or Pandoc with LaTeX engine (fallback) — macOS: `brew install pandoc` and `brew install --cask mactex`

### heic_jpg.py
Converts HEIC images (typically from iPhone/iPad) to JPG files.

**Usage:**
```bash
python backend/heic_jpg.py
```

**Python packages:**
- pillow>=11.3.0
- pillow-heif>=0.22.0

**How it works:**
1. Automatically processes ALL HEIC files in the `input/` folder
2. Converts images to JPG format at 95% quality
3. Saves JPG files to the `output/` folder

### jpg_pdf.py
Converts JPG/JPEG images to PDF files.

**Usage:**
```bash
python backend/jpg_pdf.py
```

**Python packages:**
- pillow>=11.3.0

**How it works:**
1. Automatically processes ALL JPG/JPEG files in the `input/` folder
2. Converts images to PDF format
3. Saves PDF files to the `output/` folder
4. Shows summary of successful/failed conversions

### png_pdf.py
Converts PNG images to PDF files.

**Usage:**
```bash
python backend/png_pdf.py
```

**Python packages:**
- pillow>=11.3.0

**How it works:**
1. Automatically processes ALL PNG files in the `input/` folder
2. Converts images to PDF format (handles transparency by converting to RGB)
3. Saves PDF files to the `output/` folder
4. Shows summary of successful/failed conversions

### pptx_pdf.py
Converts PowerPoint (.pptx) files to PDF using LibreOffice.

**Usage:**
```bash
python backend/pptx_pdf.py
```

**Python packages:**
- None beyond the standard library

**System requirements:**
- LibreOffice (macOS: `brew install --cask libreoffice`)
- Alternative: Add symlink if LibreOffice is installed as .app:
  ```bash
  sudo ln -s /Applications/LibreOffice.app/Contents/MacOS/soffice /usr/local/bin/soffice
  ```

**How it works:**
1. Automatically processes ALL PPTX files in the `input/` folder
2. Uses LibreOffice headless mode to convert to PDF
3. Saves PDF files to the `output/` folder
4. Shows summary of successful/failed conversions

### pptx_md.py
Converts PowerPoint (.pptx) files to Markdown format.

**Usage:**
```bash
python backend/pptx_md.py
```

**Python packages:**
- python-pptx>=1.0.2

**How it works:**
1. Automatically processes ALL PPTX files in the `input/` folder
2. Extracts text from each slide and formats as markdown
3. Each slide becomes a separate section with headers
4. Saves markdown files to the `output/` folder

**Features:**
- Extracts all text content from slides
- Formats slide titles as headers
- Separates slides with horizontal rules
- Preserves text structure and order

### heic_md.py
Converts HEIC images (typically from iPhone/iPad) to Markdown using OCR.

**Usage:**
```bash
python backend/heic_md.py
```

**Python packages:**
- pytesseract>=0.3.13
- pillow>=11.3.0
- pillow-heif>=0.22.0

**System requirements:**
- Tesseract OCR (macOS: `brew install tesseract`)

**How it works:**
1. Automatically processes ALL HEIC files in the `input/` folder
2. Preprocesses images in memory for better OCR accuracy
3. Extracts text using OCR and formats as markdown
4. Saves markdown files to the `output/` folder

**Features:**
- No intermediate JPG file saved — processes HEIC images directly in memory
- Image preprocessing for better OCR accuracy
- Text cleaning and formatting
- Sentence structure preservation

### jpg_md.py
Converts JPG/JPEG images to Markdown using OCR.

**Usage:**
```bash
python backend/jpg_md.py
```

**Python packages:**
- pytesseract>=0.3.13
- pillow>=11.3.0

**System requirements:**
- Tesseract OCR (macOS: `brew install tesseract`)

**How it works:**
1. Automatically processes ALL JPG/JPEG files in the `input/` folder
2. Preprocesses images for better OCR accuracy
3. Extracts text using OCR and formats as markdown
4. Saves markdown files to the `output/` folder

**Features:**
- Image preprocessing for better OCR
- Text cleaning and formatting
- Sentence structure preservation

### docx_pdf.py
Converts Microsoft Word (.docx) files to PDF format with proper table rendering, image extraction, and formatting preservation.

**Usage:**
```bash
# Option A: Convert all DOCX files in input/ directory
python backend/docx_pdf.py

# Option B: Convert specific file
python backend/docx_pdf.py file.docx [output.pdf]

# Option C: Use custom input/output directories
python backend/docx_pdf.py --input-dir myinput --output-dir myoutput
```

**Python packages:**
- reportlab>=4.4.4
- python-docx>=1.1.2
- pillow>=11.3.0

**How it works:**
1. Automatically processes ALL DOCX files in the `input/` folder
2. Extracts text, tables, and images from Word documents
3. Creates PDF with proper formatting, table rendering, and embedded images
4. Saves PDF files to the `output/` folder
5. Shows summary of successful/failed conversions

**Features:**
- Clean text formatting and spacing
- **Text formatting preservation** (bold, italic, underline)
- **Image extraction and embedding** with proper sizing
- **Proper text/image ordering** - maintains document structure
- Table rendering with borders and proper layout
- Preserves document structure (paragraphs, tables, and images in order)
- Support for UTF-8 encoding and special characters
- Custom input/output directories support

### sql_pdf.py
Converts SQL files to PDF format with syntax highlighting and proper formatting.

**Usage:**
```bash
# Option A: Convert all SQL files in input/ directory
python backend/sql_pdf.py

# Option B: Convert specific file
python backend/sql_pdf.py file.sql [output.pdf]
```

**Python packages:**
- reportlab>=4.4.4

**How it works:**
1. Automatically processes ALL SQL files in the `input/` folder
2. Formats SQL with proper indentation and keyword highlighting
3. Creates PDF with syntax highlighting and clean formatting
4. Saves PDF files to the `output/` folder
5. Shows summary of successful/failed conversions

**Features:**
- SQL syntax highlighting
- Proper code formatting and indentation
- Clean PDF layout with title and formatted code blocks
- Support for all SQL dialects (MySQL, PostgreSQL, SQLite, etc.)

### txt_pdf.py
Converts text (.txt) files to PDF format with clean formatting.

**Usage:**
```bash
# Option A: Convert all TXT files in input/ directory
python backend/txt_pdf.py

# Option B: Convert specific file
python backend/txt_pdf.py file.txt [output.pdf]
```

**Python packages:**
- reportlab>=4.4.4

**How it works:**
1. Automatically processes ALL TXT files in the `input/` folder
2. Creates PDF with clean formatting and readable fonts
3. Saves PDF files to the `output/` folder
4. Shows summary of successful/failed conversions

**Features:**
- Clean text formatting
- Proper line breaks and spacing
- Support for UTF-8 encoding

### R_Rmd.py
Converts R (.R) files to R Markdown (.Rmd) format.

**Usage:**
```bash
# Option A: Convert all R files in input/ directory
python backend/R_Rmd.py

# Option B: Convert specific file
python backend/R_Rmd.py file.R [output.Rmd]

# Option C: Use custom input/output directories
python backend/R_Rmd.py --input-dir myinput --output-dir myoutput
```

**Python packages:**
- None beyond the standard library

**How it works:**
1. Reads R file and converts comments to markdown text
2. Wraps code sections in R code chunks (```{r} ... ```)
3. Formats headers and removes separator lines
4. Groups related code into logical chunks
5. Saves Rmd files to the `output/` folder

**Features:**
- Converts R comments to markdown text
- Groups code into logical chunks
- Formats section headers properly
- Removes separator lines (===)
- Formats name/ID at the top
- Limits empty lines for clean output

### Rmd_pdf.py
Converts R Markdown (.Rmd) files to PDF. Prefers R's rmarkdown; falls back to pandoc if R unavailable.

**Usage:**
```bash
python backend/Rmd_pdf.py file.Rmd [output.pdf]
```

**Python packages:**
- None beyond the standard library

**System requirements:**
- R with rmarkdown package (recommended for R code execution)
  ```bash
  # Install R (macOS)
  brew install r
  # Install rmarkdown package
  Rscript -e 'install.packages("rmarkdown")'
  ```
- or Pandoc with LaTeX engine (fallback) — macOS: `brew install pandoc` and `brew install --cask mactex`

**How it works:**
1. Tries R's rmarkdown first (executes R code chunks)
2. Falls back to pandoc if R unavailable (treats as plain markdown)
3. Saves PDF files to the `output/` folder

### combine_files.py
Combines multiple files into one output file. Automatically detects file types and combines accordingly.

**Usage:**
```bash
# Combine all files in input/ folder (auto-detects format)
python backend/combine_files.py

# Combine specific files
python backend/combine_files.py file1.jpg file2.jpg

# Combine with custom output name
python backend/combine_files.py file1.pdf file2.pdf combined.pdf
```

**Python packages:**
- pillow>=11.3.0
- pypdf>=6.0.0

**How it works:**
1. Reads files from the `input/` folder (or specified files)
2. Automatically detects file types and combines:
   - **Images** (JPG, PNG, GIF, BMP, TIFF, WEBP) → stacks vertically into one image (`combined.jpg`)
   - **PDFs** → merges all pages into one PDF (`combined.pdf`)
   - **Text files** → concatenates with separators showing filenames (`combined.txt`)
3. Saves combined file to the `output/` folder
4. Skips system files like `.DS_Store`

**Features:**
- Auto-detects output format based on input files (JPG→JPG, PDF→PDF, etc.)
- Images are stacked vertically in a single image file
- Text files are concatenated with clear file separators
- PDFs are merged preserving all pages in order
- Handles mixed file types gracefully

## Folder Structure
```
converter/
├── backend/                # All Python code
│   ├── input/              # Put your source files here
│   ├── output/             # Converted files will appear here
│   ├── server.py           # FastAPI server behind the web UI
│   ├── agent.py            # AI agent for interactive file conversion
│   ├── xlsx_csv.py         # Excel to CSV converter
│   ├── csv_xlsx.py         # CSV to Excel converter
│   ├── csv_md.py           # CSV to Markdown converter
│   ├── pdf_md.py           # PDF to Markdown converter (pymupdf4llm + OCR)
│   ├── openai_pdf_md.py    # PDF to Markdown converter (AI-powered)
│   ├── ss_txt.py           # Screenshot to text converter (OCR; --structured for tables)
│   ├── ipynb_pdf.py        # Jupyter notebook to PDF converter
│   ├── md_pdf.py           # Markdown to PDF converter (Pandoc, enhanced)
│   ├── html_pdf.py         # HTML to PDF converter (wkhtmltopdf/Pandoc)
│   ├── heic_jpg.py         # HEIC to JPG converter
│   ├── heic_md.py          # HEIC to Markdown converter (OCR)
│   ├── jpg_pdf.py          # JPG/JPEG to PDF converter
│   ├── jpg_md.py           # JPG/JPEG to Markdown converter (OCR)
│   ├── jpg_ocr.py          # JPG/JPEG to plain text converter (OCR)
│   ├── png_pdf.py          # PNG to PDF converter
│   ├── combine_files.py    # File combiner (PDFs, images, text)
│   ├── pptx_pdf.py         # PowerPoint to PDF converter (LibreOffice)
│   ├── pptx_md.py          # PowerPoint to Markdown converter
│   ├── docx_pdf.py         # Word to PDF converter
│   ├── R_Rmd.py            # R to R Markdown converter
│   ├── Rmd_pdf.py          # R Markdown to PDF converter
│   ├── sql_pdf.py          # SQL to PDF converter
│   └── txt_pdf.py          # TXT to PDF converter
├── frontend/               # All TypeScript code (Vite + React)
│   ├── index.html
│   └── src/
│       ├── App.tsx         # The entire UI
│       ├── api.ts          # Backend calls
│       └── types.ts        # Shared types
├── pyproject.toml          # Python package dependencies
└── .env                    # Store your OpenAI API key here (optional)
```

**Note:** `input/` and `output/` live inside `backend/`, since that's where the
converting happens. Every script resolves those folders relative to its own file, so
they work the same no matter which directory you run from.

## Requirements

- **Python:** 3.11 or higher

## Installation

1. **Install Python dependencies:**
   ```bash
   # Using uv (recommended)
   uv sync
   
   # Or using pip
   pip install -e .
   ```

2. **Create the required folders** (if they don't exist):
   ```bash
   mkdir -p backend/input backend/output
   ```

3. **Install system dependencies** (as needed):
   - **Tesseract OCR** (required for OCR features): `brew install tesseract`
     - Note: This must be installed via brew, not through Python packages
   - Pandoc: `brew install pandoc` (for markdown/HTML conversions)
   - LaTeX: `brew install --cask mactex` (for PDF generation)
   - LibreOffice: `brew install --cask libreoffice` (for PowerPoint conversion)
   - mermaid-filter (for Mermaid diagrams in `md_pdf.py`): `pnpm add -g mermaid-filter`

4. **Optional: Set up OpenAI API key** (for `openai_pdf_md.py` and `agent.py`):
   ```bash
   # Create .env file
   echo "OPENAI_API_KEY=your_api_key_here" > .env
   ```

## Keeping Up to Date

To keep your environment synchronized with the latest dependencies:

```bash
# From the project root directory
uv sync

# Or update dependencies to latest compatible versions
uv sync --upgrade
```

## How to Use

### Using the AI Agent (Recommended)
1. Put your files in the `input` folder
2. Run: `file-convert-agent` (or `python backend/agent.py`)
3. Ask the agent to convert files using natural language
4. Find converted files in the `output` folder

### Using Individual Scripts
1. Put your files in the `input` folder
2. Run the appropriate conversion script (e.g., `python backend/md_pdf.py`)
3. Find converted files in the `output` folder

### File Overwriting
**Important:** Converting the same file multiple times will automatically overwrite the existing output file. For example:
- First conversion: `mock2.md` → `output/mock2.pdf` (creates new file)
- Second conversion: `mock2.md` → `output/mock2.pdf` (overwrites the existing PDF)

This means you can update your source file and convert it again to get an updated PDF without needing to delete the old one first.

## How the Web UI Works

To add a conversion to the UI, add one row to the `REGISTRY` list in
`backend/server.py`. The frontend hardcodes no formats, it asks `/api/formats`.

Each request runs in a scratch workspace under `.webui_jobs/<uuid>/`, so the web UI
never touches your real `backend/input/` and `backend/output/`. Options whose system
dependency is missing (Tesseract, Pandoc, LaTeX, LibreOffice, `OPENAI_API_KEY`) are
greyed out with the reason instead of being offered and failing.

## Supported Conversions

| From | To | Script |
|------|-----|--------|
| Markdown (.md) | PDF | `md_pdf.py` |
| PDF | Markdown (.md) | `pdf_md.py` |
| Word (.docx) | PDF | `docx_pdf.py` |
| PowerPoint (.pptx) | PDF | `pptx_pdf.py` |
| PowerPoint (.pptx) | Markdown (.md) | `pptx_md.py` |
| Excel (.xlsx) | CSV | `xlsx_csv.py` |
| CSV (.csv) | Excel (.xlsx) | `csv_xlsx.py` |
| CSV (.csv) | Markdown (.md) | `csv_md.py` |
| HTML | PDF | `html_pdf.py` |
| Text (.txt) | PDF | `txt_pdf.py` |
| SQL | PDF | `sql_pdf.py` |
| Jupyter Notebook (.ipynb) | PDF | `ipynb_pdf.py` |
| HEIC images | JPG | `heic_jpg.py` |
| HEIC images | Markdown (.md) | `heic_md.py` |
| JPG/JPEG images | PDF | `jpg_pdf.py` |
| PNG images | PDF | `png_pdf.py` |
| JPG/JPEG images | Markdown (.md) | `jpg_md.py` |
| Screenshots/Images | Text | `ss_txt.py` (`--structured` for tables) |
| R (.R) | R Markdown (.Rmd) | `R_Rmd.py` |
| R Markdown (.Rmd) | PDF | `Rmd_pdf.py` |
| Multiple files (images/PDFs/text) | Single file | `combine_files.py` |
| PDF (AI-powered) | Markdown (.md) | `openai_pdf_md.py` |

## Flows That Don't Work

Some conversion chains run without erroring but produce bad output. They're listed in
[CONVERSIONS.md](CONVERSIONS.md), along with why each one fails and what to use instead.
