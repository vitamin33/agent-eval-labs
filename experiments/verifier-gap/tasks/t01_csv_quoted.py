TASK = {
    "id": "T01",
    "name": "csv_quoted",
    "type": "data parsing with edge cases",
    "kind": "python",
    "entrypoint": "parse_csv_line",
    "prompt": (
        "Write a Python function "
        "`parse_csv_line(line: str, delimiter: str = ',') -> list[str]` that splits a "
        "single CSV record into its fields.\n\n"
        "Requirements:\n"
        "- A field may be wrapped in double quotes; the quotes are not part of the value.\n"
        "- A quoted field may contain the delimiter.\n"
        "- Inside a quoted field, a doubled double-quote (\"\") means one literal \" "
        "character.\n"
        "- Empty fields are preserved.\n"
        "- `delimiter` may be any single character, not just a comma.\n"
        "- Whitespace OUTSIDE quotes is part of the field and must be preserved exactly.\n"
        "- If a quoted field is never closed, everything from the opening quote to the "
        "end of the line is the field's value, delimiters included.\n"
        "- Do not use the `csv` module; implement the parsing yourself.\n\n"
        "Return only the function definition."
    ),
    "asserts": [
        "parse_csv_line('a,b,c') == ['a', 'b', 'c']",
        "parse_csv_line('\"a,b\",c') == ['a,b', 'c']",
        "parse_csv_line('\"say \"\"hi\"\"\",x') == ['say \"hi\"', 'x']",
        "parse_csv_line('a,,c') == ['a', '', 'c']",
        "parse_csv_line('a;b;c', ';') == ['a', 'b', 'c']",
        "parse_csv_line('\"x;y\";z', ';') == ['x;y', 'z']",
        "parse_csv_line(' a , b ') == [' a ', ' b ']",
        "parse_csv_line('\"unterminated,rest') == ['unterminated,rest']",
    ],
    "hidden_asserts": [
        "parse_csv_line('x,\"y,z\",w') == ['x', 'y,z', 'w']",
        "parse_csv_line('\"a\"\"b\"') == ['a\"b']",
        "parse_csv_line('p|q', '|') == ['p', 'q']",
        "parse_csv_line('') == ['']",
        "parse_csv_line('\"open') == ['open']",
    ],
    "reference": '''
def parse_csv_line(line, delimiter=","):
    fields, cur, i, in_q = [], [], 0, False
    while i < len(line):
        ch = line[i]
        if in_q:
            if ch == '"':
                if i + 1 < len(line) and line[i + 1] == '"':
                    cur.append('"'); i += 2; continue
                in_q = False; i += 1; continue
            cur.append(ch); i += 1
        else:
            if ch == '"':
                in_q = True; i += 1
            elif ch == delimiter:
                fields.append("".join(cur)); cur = []; i += 1
            else:
                cur.append(ch); i += 1
    fields.append("".join(cur))
    return fields
''',
    "silent_failure": '''
def parse_csv_line(line, delimiter=","):
    return line.split(delimiter)
''',
}
