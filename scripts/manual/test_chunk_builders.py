from chunk_builder import build_chunks_from_pdf, build_chunks_from_pptx, build_chunks_from_docx

def main():
    pdf_path = "uploads/B11-02-NLP Exp4.pdf"
    pptx_path = "uploads/sample1.pptx"
    docx_path = "uploads/test_style.docx"

    print("PDF chunks:", len(build_chunks_from_pdf(pdf_path, "test")))
    print("PPTX chunks:", len(build_chunks_from_pptx(pptx_path, "slides")))
    print("DOCX chunks:", len(build_chunks_from_docx(docx_path, "notes")))

if __name__ == "__main__":
    main()
