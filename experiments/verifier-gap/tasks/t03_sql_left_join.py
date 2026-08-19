FIXTURE = """
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, total REAL);
INSERT INTO customers (id, name) VALUES (1, 'Ada'), (2, 'Grace'), (3, 'Linus');
INSERT INTO orders (id, customer_id, total) VALUES
    (10, 1, 25.0),
    (11, 1, 40.0),
    (12, 3, 15.0);
"""

# A second, differently-shaped dataset. The same query must work on it, which
# is what a query written around the first fixture's data cannot do.
HIDDEN_FIXTURE = """
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, total REAL);
INSERT INTO customers (id, name) VALUES (1, 'Bob'), (2, 'Cleo'), (3, 'Dan'), (4, 'Eve');
INSERT INTO orders (id, customer_id, total) VALUES
    (20, 1, 5.0),
    (21, 3, 6.0),
    (22, 3, 7.0),
    (23, 3, 8.0);
"""

TASK = {
    "id": "T03",
    "name": "sql_left_join_count",
    "type": "SQL with subtle predicates",
    "kind": "sql",
    "entrypoint": None,
    "fixture": FIXTURE,
    "prompt": (
        "Write a single SQLite query against this schema:\n\n"
        "```sql\n"
        "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL);\n"
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, total REAL);\n"
        "```\n\n"
        "Return two columns — the customer's name and the number of orders that customer "
        "has placed.\n\n"
        "Requirements:\n"
        "- EVERY customer must appear, including customers who have never placed an order.\n"
        "- A customer with no orders must show the integer 0, not NULL.\n"
        "- Order the rows by customer name ascending.\n\n"
        "Return only the SQL query."
    ),
    "asserts": [
        "rows == [('Ada', 2), ('Grace', 0), ('Linus', 1)]",
        "len(rows) == 3",
        "dict(rows)['Grace'] == 0",
        "dict(rows)['Grace'] is not None",
        "[r[0] for r in rows] == ['Ada', 'Grace', 'Linus']",
        "all(isinstance(r[1], int) for r in rows)",
    ],
    "hidden_fixture": HIDDEN_FIXTURE,
    "hidden_asserts": [
        "rows2 == [('Bob', 1), ('Cleo', 0), ('Dan', 3), ('Eve', 0)]",
        "len(rows2) == 4",
        "dict(rows2)['Eve'] == 0",
    ],
    "reference": """
SELECT c.name, COUNT(o.id) AS order_count
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
GROUP BY c.id, c.name
ORDER BY c.name ASC;
""",
    # INNER JOIN silently drops Grace: the shape of the result still looks right.
    "silent_failure": """
SELECT c.name, COUNT(o.id) AS order_count
FROM customers c
JOIN orders o ON o.customer_id = c.id
GROUP BY c.id, c.name
ORDER BY c.name ASC;
""",
}
