FIXTURE = """
CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE orders (id INTEGER PRIMARY KEY, product_id INTEGER, qty INTEGER);
INSERT INTO products (id, name) VALUES
    (1, 'Widget'), (2, 'Gizmo'), (3, 'Sprocket'), (4, 'Cog');
INSERT INTO orders (id, product_id, qty) VALUES
    (100, 2, 3),
    (101, 4, 1),
    (102, NULL, 7);
"""

TASK = {
    "id": "T04",
    "name": "sql_not_in_null",
    "type": "SQL with subtle predicates",
    "kind": "sql",
    "entrypoint": None,
    "fixture": FIXTURE,
    "prompt": (
        "Write a single SQLite query against this schema:\n\n"
        "```sql\n"
        "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL);\n"
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, product_id INTEGER, qty INTEGER);\n"
        "```\n\n"
        "Return one column: the name of every product that has NEVER been ordered.\n\n"
        "Requirements:\n"
        "- `orders.product_id` is nullable and some rows do have a NULL product_id; those "
        "rows record an order against no product and must not suppress the result.\n"
        "- Return only the product name column.\n\n"
        "Return only the SQL query."
    ),
    "asserts": [
        "sorted(rows) == [('Sprocket',), ('Widget',)]",
        "len(rows) == 2",
        "rows != []",
        "('Gizmo',) not in rows",
        "('Cog',) not in rows",
        "all(len(r) == 1 for r in rows)",
    ],
    "reference": """
SELECT p.name
FROM products p
WHERE NOT EXISTS (
    SELECT 1 FROM orders o WHERE o.product_id = p.id
);
""",
    # NOT IN against a subquery containing NULL evaluates to UNKNOWN for every
    # row, so this returns the empty set. It looks completely reasonable.
    "silent_failure": """
SELECT p.name
FROM products p
WHERE p.id NOT IN (SELECT o.product_id FROM orders o);
""",
}
