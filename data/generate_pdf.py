"""
Helper script to generate a sample PDF invoice using basic text canvas formatting or pypdf.
"""
from pypdf import PageObject, PdfWriter
import io

def generate_sample_pdf(output_path: str):
    # Create simple PDF document
    writer = PdfWriter()
    page = PageObject.create_blank_page(width=612, height=792)
    writer.add_page(page)
    
    # We can write PDF metadata and text representation
    with open(output_path, "wb") as f:
        writer.write(f)

if __name__ == "__main__":
    generate_sample_pdf("data/invoices/sample_invoice_placeholder.pdf")
    print("PDF utility ready.")
