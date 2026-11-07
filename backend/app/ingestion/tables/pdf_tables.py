import os

# camelot and pdfplumber are imported inside each function: camelot alone costs seconds at
# import, and every app start reaches this module through the unified parser.

def extract_tables_camelot(pdf_path):
    """
    Extract tables from a PDF using Camelot.
    Returns a list of DataFrames.
    """
    import camelot

    tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
    dfs = [table.df for table in tables]
    return dfs

def extract_tables_pdfplumber(pdf_path):
    """
    Extract tables from a PDF using pdfplumber.
    Returns a list of DataFrames.
    """
    import pandas as pd
    import pdfplumber

    dfs = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                df = pd.DataFrame(table[1:], columns=table[0])
                dfs.append(df)
    return dfs
