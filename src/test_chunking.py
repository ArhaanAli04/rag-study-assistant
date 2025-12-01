from pdf_utils import extract_pdf_text, extract_pdf_metadata
from chunking import chunk_pdf

# Change this to the path of your PDF in 'uploads/'
pdf_path = "uploads/B11-02-NLP Exp4.pdf"

pages = extract_pdf_text(pdf_path)
meta = extract_pdf_metadata(pdf_path)
chunks = chunk_pdf(pdf_path)

print("PDF Metadata:", meta)

print("Chunks:")
for chunk in chunks:
    print(f"Page {chunk['page_num']} - Chunk {chunk['chunk_num']} - Length: {len(chunk['text'])}")
    print("---- Chunk Content ----")
    print(chunk['text'])
    print("-----------------------\n")
