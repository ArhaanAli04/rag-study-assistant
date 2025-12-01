from pptx_utils import extract_pptx_text, extract_pptx_metadata
from pptx_pipeline import process_pptx

pptx_path = "uploads/sample1.pptx"

# Extract metadata
metadata = extract_pptx_metadata(pptx_path)
print("PPTX Metadata:", metadata)

# Process full pipeline
result = process_pptx(pptx_path)

print(f"\nTotal Slides: {metadata['num_slides']}")
print(f"\nTables Found: {len(result['tables'])}")

print("\nSlide Processing Results:")
for slide in result["slides"]:
    print(f"\nSlide {slide['slide_num']}: {slide['title']}")
    print(f"  Chunks: {len(slide['chunks'])}")
    for chunk in slide["chunks"]:
        print(f"    Chunk {chunk['chunk_num']} - Length: {len(chunk['text'])}")
        print(f"    Preview: {chunk['text'][:200]}...")
