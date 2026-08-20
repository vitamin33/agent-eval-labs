FIXTURE = """
CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE orders (id INTEGER PRIMARY KEY, product_id INTEGER, qty INTEGER);
INSERT INTO products (id, name) VALUES
    (1, 'Widget'), (2, 'Gizmo'), (3, 'Sprocket'), (4, 'Cog'), (5, 'Flange');
INSERT INTO orders (id, product_id, qty) VALUES
    (100, 2, 3),
    (101, 4, 1),
    (102, NULL, 7),
    (103, 5, 0),
    (104, 5, NULL);
"""

HIDDEN_FIXTURE = """
CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE orders (id INTEGER PRIMARY KEY, product_id INTEGER, qty INTEGER);
INSERT INTO products (id, name) VALUES (1, 'Alpha'), (2, 'Beta'), (3, 'Gamma'), (4, 'Delta');
INSERT INTO orders (id, product_id, qty) VALUES
    (200, 3, 1),
    (201, NULL, 2),
    (202, 4, 0),
    (203, 4, NULL);
"""

TASK = {
    "id": "T04",
    "name": "sql_not_in_null",
    "type": "SQL with subtle predicates",
    "kind": "sql",
    "entrypoint": None,
    "fixture": FIXTURE,
    "hidden_fixture": HIDDEN_FIXTURE,
    "prompt": (
        "Write a single SQLite query against this schema:\n\n"
        "```sql\n"
        "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL);\n"
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, product_id INTEGER, qty INTEGER);\n"
        "```\n\n"
        "Return one column: the name of every product that has never been genuinely "
        "ordered, sorted by name ascending.\n\n"
        "Requirements:\n"
        "- An order counts only if it has a positive quantity. An order row with "
        "`qty = 0` or `qty IS NULL` does NOT count as having ordered that product.\n"
        "- `orders.product_id` is nullable and some rows do have a NULL product_id; "
        "those rows record an order against no product and must not suppress the "
        "result.\n"
        "- Return only the product name column.\n\n"
        "Return only the SQL query."
    ),
    "asserts": [
        "rows == [('Flange',), ('Sprocket',), ('Widget',)]",
        "len(rows) == 3",
        "rows != []",
        "('Flange',) in rows",
        "('Gizmo',) not in rows",
        "all(len(r) == 1 for r in rows)",
    ],
    "hidden_asserts": [
        "rows2 == [('Alpha',), ('Beta',), ('Delta',)]",
        "len(rows2) == 3",
        "('Gamma',) not in rows2",
    ],
    "reference": """
SELECT p.name
FROM products p
WHERE NOT EXISTS (
    SELECT 1 FROM orders o
    WHERE o.product_id = p.id AND o.qty IS NOT NULL AND o.qty > 0
)
ORDER BY p.name ASC;
""",
    # Two traps at once: NOT IN against a subquery containing NULL is UNKNOWN for
    # every row and returns nothing, and `qty > 0` inside the subquery silently
    # drops the NULL-qty rows from the exclusion set in a way that looks right.
    "silent_failure": """
SELECT p.name
FROM products p
WHERE p.id NOT IN (SELECT o.product_id FROM orders o WHERE o.qty > 0)
ORDER BY p.name ASC;
""",
}
