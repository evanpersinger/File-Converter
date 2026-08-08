# Conversions To Avoid

Conversion chains that run without erroring but produce bad output. Nothing here
crashes, which is exactly why it's worth writing down: the script reports success and
you only notice the problem when you read the result.

Avoid these. Use the alternative listed instead.

More entries get added here as they turn up.

## JPG to PDF to Markdown

**Chain:** `jpg_pdf.py` then `pdf_md.py`

**Why it breaks:** `jpg_pdf.py` embeds the image at 100 DPI and adds no text layer. When
`pdf_md.py` opens that PDF it sees a page with no extractable text, treats it as scanned,
and falls back to OCR by re-rendering the embedded 100 DPI image at 300 DPI. Upscaling a
low-resolution image does not recover detail that was never captured, so the OCR reads a
blurry render instead of the original photo.

**Do this instead:** run `jpg_md.py` on the JPG directly. It OCRs the source image at full
resolution and skips the lossy PDF round trip entirely.

## Many images to one combined image to PDF to Markdown

**Chain:** `combine_files.py` then `jpg_pdf.py` then `openai_pdf_md.py`

**Why it breaks:** `combine_files.py` stacks images vertically into one very tall image, so
the resulting PDF is a single enormous page rather than several normal ones.
`openai_pdf_md.py` then has to hand that whole thing to OpenAI's Vision API as one image.
Conversion takes a very long time and can fail outright.

**Do this instead:** convert each image to PDF individually with `jpg_pdf.py` or
`png_pdf.py`, combine those PDFs with `combine_files.py`, then run `openai_pdf_md.py`. You
get a real multi-page PDF, and the Vision API processes it page by page, much faster.
