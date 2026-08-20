FIXTURE = """
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, total REAL, status TEXT);
INSERT INTO customers (id, name) VALUES (1, 'Ada'), (2, 'Grace'), (3, 'Linus');
INSERT INTO orders (id, customer_id, total, status) VALUES
    (10, 1, 25.0, 'shipped'),
    (11, 1, 40.0, 'shipped'),
    (12, 1, 99.0, 'cancelled'),
    (13, 3, 15.0, 'shipped');
"""

HIDDEN_FIXTURE = """
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, total REAL, status TEXT);
INSERT INTO customers (id, name) VALUES (1, 'Bob'), (2, 'Cleo'), (3, 'Dan'), (4, 'Eve');
INSERT INTO orders (id, customer_id, total, status) VALUES
    (20, 1, 5.0, 'shipped'),
    (21, 3, 6.0, 'shipped'),
    (22, 3, 7.0, 'shipped'),
    (23, 3, 8.0, 'cancelled'),
    (24, 4, 50.0, 'cancelled');
"""

TASK = {
    "id": "T03",
    "name": "sql_left_join_count",
    "type": "SQL with subtle predicates",
    "kind": "sql",
    "entrypoint": None,
    "fixture": FIXTURE,
    "hidden_fixture": HIDDEN_FIXTURE,
    "prompt": (
        "Write a single SQLite query against this schema:\n\n"
        "```sql\n"
        "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL);\n"
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, "
        "total REAL, status TEXT);\n"
        "```\n\n"
        "Return three columns: the customer's name, how many orders they have placed, "
        "and how much they have spent.\n\n"
        "Requirements:\n"
        "- Orders with `status = 'cancelled'` count for NEITHER the order count NOR the "
        "spend. All other statuses count.\n"
        "- EVERY customer must appear, including customers who have never ordered and "
        "customers whose every order was cancelled.\n"
        "- A customer with no counting orders must show the integer 0 and the float 0.0, "
        "never NULL.\n"
        "- Order by order count descending, then by name ascending.\n\n"
        "Return only the SQL query."
    ),
    "asserts": [
        "rows == [('Ada', 2, 65.0), ('Linus', 1, 15.0), ('Grace', 0, 0.0)]",
        "len(rows) == 3",
        "[r[0] for r in rows] == ['Ada', 'Linus', 'Grace']",
        "dict((r[0], r[1]) for r in rows)['Grace'] == 0",
        "dict((r[0], r[2]) for r in rows)['Grace'] == 0.0",
        "all(isinstance(r[1], int) for r in rows)",
    ],
    "hidden_asserts": [
        "rows2 == [('Dan', 2, 13.0), ('Bob', 1, 5.0), ('Cleo', 0, 0.0), ('Eve', 0, 0.0)]",
        "len(rows2) == 4",
        "dict((r[0], r[1]) for r in rows2)['Eve'] == 0",
    ],
    "reference": """
SELECT c.name,
       COUNT(CASE WHEN o.status <> 'cancelled' THEN o.id END) AS order_count,
       COALESCE(SUM(CASE WHEN o.status <> 'cancelled' THEN o.total END), 0.0) AS spend
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
GROUP BY c.id, c.name
ORDER BY order_count DESC, c.name ASC;
""",
    # Filtering the cancelled rows in WHERE instead of inside the aggregate turns
    # the LEFT JOIN back into an inner join: every customer whose orders were all
    # cancelled silently disappears, and so does every customer with no orders.
    # The query reads as obviously correct.
    "silent_failure": """
SELECT c.name,
       COUNT(o.id) AS order_count,
       COALESCE(SUM(o.total), 0.0) AS spend
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
WHERE o.status <> 'cancelled'
GROUP BY c.id, c.name
ORDER BY order_count DESC, c.name ASC;
""",
}
