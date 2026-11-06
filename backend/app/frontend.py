import streamlit as st

def main():
    st.title("RAG Study Assistant - Upload your study materials")

    uploaded_file = st.file_uploader("Upload your study files (PDF, PPTX, DOCX, images...)")

    if uploaded_file is not None:
        st.write(f"Uploaded file: {uploaded_file.name}")
        # Place for future: Send to backend / process / show answers

if __name__ == "__main__":
    main()
