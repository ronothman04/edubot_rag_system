with open('backend/rag.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "you MUST return exactly:" in line and "NOT_FOUND_MESSAGE" in line:
        # replace the line
        lines[i] = "        f\"- IMPORTANT: If the student asks about a specific course/subject, do NOT provide generic admission information. If the context does not explicitly mention that specific course/subject, you MUST return exactly: \\\"{NOT_FOUND_MESSAGE}\\\"\\n\"\n"
        break

with open('backend/rag.py', 'w') as f:
    f.writelines(lines)
print("Fixed!")
