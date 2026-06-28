import pypdf

def main():
    path = 'backend/data/uploads/Prospectus2026.pdf'
    reader = pypdf.PdfReader(path)
    print(f"Total pages in Prospectus2026.pdf: {len(reader.pages)}")
    
    for page_num, page in enumerate(reader.pages):
        text = page.extract_text()
        if not text:
            continue
        text_lower = text.lower()
        
        # Check if MCA or Computer Application is on this page
        if 'mca' in text_lower or 'computer application' in text_lower:
            print(f"--- Page {page_num + 1} contains MCA/Computer Application ---")
            lines = text.split('\n')
            for line in lines[:10]: # Print first 10 lines of the page
                print("  ", line.strip())
            print("-" * 50)
            
        # Check if Fee/Fees/Charges is on this page
        if 'fee' in text_lower or 'fees' in text_lower or 'charges' in text_lower:
            print(f"--- Page {page_num + 1} contains Fee/Fees/Charges ---")
            lines = text.split('\n')
            for line in lines[:10]: # Print first 10 lines of the page
                print("  ", line.strip())
            print("-" * 50)

if __name__ == '__main__':
    main()
