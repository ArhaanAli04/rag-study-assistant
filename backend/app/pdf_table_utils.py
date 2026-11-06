import camelot
import pdfplumber
import os

def extract_tables_camelot(pdf_path):
    """
    Extract tables from a PDF using Camelot.
    Returns a list of DataFrames.
    """
    tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
    dfs = [table.df for table in tables]
    return dfs

def extract_tables_pdfplumber(pdf_path):
    """
    Extract tables from a PDF using pdfplumber.
    Returns a list of DataFrames.
    """
    import pandas as pd
    dfs = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                df = pd.DataFrame(table[1:], columns=table[0])
                dfs.append(df)
    return dfs
