import os
import pypdf

def main():
    uploads_dir = 'backend/data/uploads'
    for filename in os.listdir(uploads_dir):
        if not filename.endswith('.pdf'):
            continue
        path = os.path.join(uploads_dir, filename)
        try:
            reader = pypdf.PdfReader(path)
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text()
                if not text:
                    continue
                text_lower = text.lower()
                if 'mca' in text_lower and ('fee' in text_lower or 'cost' in text_lower or 'charge' in text_lower):
                    print(f"Match found in {filename} (page {page_num + 1}):")
                    lines = text.split('\n')
                    for line in lines:
                        if 'mca' in line.lower() or 'fee' in line.lower() or 'cost' in line.lower():
                            print("  ", line.strip()[:100])
                    print("-" * 50)
        except Exception as e:
            print(f"Error reading {filename}: {e}")

if __name__ == '__main__':
    main()
