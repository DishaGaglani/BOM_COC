FROM python:3.12-slim

# poppler-utils: PDF -> image rendering (unstructured's pdf partitioner)
# tesseract-ocr: OCR for scanned PDFs/images
# libmagic1: file type detection
RUN apt-get update && apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
# CPU-only torch: pulling the default (CUDA) build resolves multi-GB wheels
# this GPU-less VM will never use. Needed by unstructured's table-structure
# (Table Transformer) model, not just the layout model.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-fetch, at build time (with reliable network), everything `unstructured`
# would otherwise lazily download on the VM at first-request time:
#  - NLTK tokenizer data, via NLTK's own downloader — unstructured 0.15.13's
#    bundled downloader points at a now-dead S3 mirror (403).
#  - The hi_res layout model (yolox) and table-structure model
#    (Table Transformer), by running a real parse against a throwaway PDF.
# Without this, the first document parsed on the VM stalls on these
# downloads (and hangs indefinitely if the VM has no/slow internet egress).
ENV NLTK_DATA=/usr/local/share/nltk_data
RUN python -c "\
import nltk, os; \
[nltk.download(p, download_dir=os.environ['NLTK_DATA']) for p in \
    ['punkt', 'punkt_tab', 'averaged_perceptron_tagger', 'averaged_perceptron_tagger_eng']]"
RUN python -c "\
from unstructured.partition.auto import partition; \
partition(filename='scripts/_warmup/sample.pdf', strategy='hi_res', skip_infer_table_types=[], languages=['eng'])"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
