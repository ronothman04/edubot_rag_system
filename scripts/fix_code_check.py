with open('backend/rag.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "context, sources = build_context(" in line:
        context_build_idx = i
        break

# Insert the check right after context is built.
# let's find the `if not context:` block which is right after
for i, line in enumerate(lines[context_build_idx:]):
    if "if not context:" in line:
        insert_idx = context_build_idx + i
        break

# We will insert our check right before `if not context:`
code_to_insert = """    if context and personal_case:
        target_to_check = eligibility_case.get("target_course") or eligibility_case.get("subject")
        if target_to_check:
            # Check if target is actually in context
            t_lower = normalize_query(target_to_check)
            c_lower = normalize_query(context)
            if t_lower not in c_lower:
                return not_found_response(
                    query=retrieval_query,
                    where_filter=where_filter,
                    used_history=used_history,
                    original_query=query,
                )
"""
lines.insert(insert_idx, code_to_insert)

with open('backend/rag.py', 'w') as f:
    f.writelines(lines)
print("Code check added!")
