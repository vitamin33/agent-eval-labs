TASK = {
    "id": "T01",
    "name": "csv_quoted",
    "type": "data parsing with edge cases",
    "kind": "python",
    "entrypoint": "parse_csv_line",
    "prompt": (
        "Write a Python function `parse_csv_line(line: str) -> list[str]` that splits a "
        "single CSV record into its fields, following RFC 4180.\n\n"
        "Requirements:\n"
        "- A field may be wrapped in double quotes; the quotes are not part of the value.\n"
        "- A quoted field may contain commas.\n"
        "- Inside a quoted field, a doubled double-quote (\"\") means one literal \" character.\n"
        "- Empty fields are preserved.\n"
        "- Do not use the `csv` module; implement the parsing yourself.\n\n"
        "Return only the function definition."
    ),
    "asserts": [
        "parse_csv_line('a,b,c') == ['a', 'b', 'c']",
        "parse_csv_line('\"a,b\",c') == ['a,b', 'c']",
        "parse_csv_line('\"say \"\"hi\"\"\",x') == ['say \"hi\"', 'x']",
        "parse_csv_line('a,,c') == ['a', '', 'c']",
        "parse_csv_line('') == ['']",
        "parse_csv_line('\"\",x') == ['', 'x']",
    ],
    "hidden_asserts": [
        "parse_csv_line('x,\"y,z\",w') == ['x', 'y,z', 'w']",
        "parse_csv_line('\"a\"\"b\"') == ['a\"b']",
        "parse_csv_line(',') == ['', '']",
        "parse_csv_line('one') == ['one']",
    ],
    "reference": '''
def parse_csv_line(line):
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
            elif ch == ',':
                fields.append(''.join(cur)); cur = []; i += 1
            else:
                cur.append(ch); i += 1
    fields.append(''.join(cur))
    return fields
''',
    # The natural first implementation: right on the obvious case, wrong on quotes.
    "silent_failure": '''
def parse_csv_line(line):
    return line.split(",")
''',
}
