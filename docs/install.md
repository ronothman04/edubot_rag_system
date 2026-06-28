# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate

# Install dependencies
pip install pdfplumber
pip install streamlit //for python library
pip install sentence-transformers
pip install chromadb
pip install requests
pip install "fastapi[all]"
brew install tesseract
pip install docx2txt

# Frontend Installed
npm create vite@latest my-react-app -- --template react

npm install @supabase/supabase-js lucide-react react react-dom react-hot-toast recharts

# Frontend Dependencies
@supabase/supabase-js ^2.105.1
lucide-react ^1.14.0
react ^19.2.5
react-dom ^19.2.5
react-hot-toast ^2.6.0
recharts ^3.8.1

# Frontend Dev Dependencies
@eslint/js ^10.0.1
@types/react ^19.2.14
@types/react-dom ^19.2.3
@vitejs/plugin-react ^6.0.1
autoprefixer ^10.5.0
eslint ^10.2.1
eslint-plugin-react-hooks ^7.1.1
eslint-plugin-react-refresh ^0.5.2
globals ^17.5.0
postcss ^8.5.13
tailwindcss ^3.4.1
vite ^8.0.10
npm install react-markdown remark-gfm
