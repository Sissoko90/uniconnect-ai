FROM python:3.12-slim

WORKDIR /app

# Unicode fonts, for the PDFs the bot builds. The fonts built into the PDF
# library cannot write an accented character, and translating the group's
# documents into French is the entire point of that feature.
#
# This package carries the sans, its bold and the serif, which is the whole
# palette the documents are set in: the banner and the lead paragraph in
# bold, the section headings in serif. Check what landed with
#   docker compose exec -T api python -c "import pdf; print(pdf.fonts())"
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

# Dependencies in their own layer: editing main.py must not reinstall them.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
