"""Fixture data for experiment 3: experiment 2's orderdesk with Amendment A1.

Plain literals, no generation. Every ground-truth assert is computed from
these, so they must be identical on every machine and every run.

What changed against experiment 2, and why (RESEARCH.md, Amendment A1):

* O01 total 120.00 -> 320.00: C1's order is now EU's largest pending order,
  so a wrong region for C1 changes T8's answer instead of nothing.
* O02 now has a shipment record, so T5's only positive is O14.
* O13 belongs to C3 (it was the orphan); still pending, 88.00.
* O14 added: C4, shipped, 58.20, NO shipment record. Gives T2 a two-element
  sum (off_by_one needs two) and gives T5 a positive that sits last in
  list_orders(shipped), where omission drops it.
* O15 added: C9 (does not exist), pending, 20.00. The orphan T3 must find,
  with the highest id so omission drops it, and below T6's threshold so
  omission makes T6 miss a cancellation.
"""

from __future__ import annotations

# region is deliberately NOT stored on the order: resolving it requires a join
# through the customer, which is what makes the `wrong_field` injection able to
# poison a downstream aggregate.
CUSTOMERS = [
    {"id": "C1", "name": "Alder",   "region": "EU"},
    {"id": "C2", "name": "Birch",   "region": "EU"},
    {"id": "C3", "name": "Cedar",   "region": "US"},
    {"id": "C4", "name": "Dogwood", "region": "US"},
    {"id": "C5", "name": "Elm",     "region": "APAC"},
    {"id": "C6", "name": "Fir",     "region": "APAC"},
]

ORDERS = [
    {"id": "O01", "customer_id": "C1", "total": 320.00, "status": "pending"},
    {"id": "O02", "customer_id": "C1", "total": 45.50,  "status": "shipped"},
    {"id": "O03", "customer_id": "C2", "total": 310.00, "status": "pending"},
    {"id": "O04", "customer_id": "C2", "total": 12.25,  "status": "cancelled"},
    {"id": "O05", "customer_id": "C3", "total": 89.99,  "status": "pending"},
    {"id": "O06", "customer_id": "C3", "total": 260.00, "status": "shipped"},
    {"id": "O07", "customer_id": "C4", "total": 15.00,  "status": "pending"},
    {"id": "O08", "customer_id": "C4", "total": 430.75, "status": "shipped"},
    {"id": "O09", "customer_id": "C5", "total": 77.40,  "status": "pending"},
    {"id": "O10", "customer_id": "C5", "total": 9.99,   "status": "cancelled"},
    {"id": "O11", "customer_id": "C6", "total": 505.10, "status": "pending"},
    {"id": "O12", "customer_id": "C6", "total": 63.00,  "status": "shipped"},
    {"id": "O13", "customer_id": "C3", "total": 88.00,  "status": "pending"},
    {"id": "O14", "customer_id": "C4", "total": 58.20,  "status": "shipped"},
    {"id": "O15", "customer_id": "C9", "total": 20.00,  "status": "pending"},
]

# Shipment records are the independent route to a status. O14 is marked
# shipped with no shipment record: T5's positive.
SHIPMENTS = [
    {"order_id": "O02", "carrier": "DHL"},
    {"order_id": "O06", "carrier": "DHL"},
    {"order_id": "O08", "carrier": "UPS"},
    {"order_id": "O12", "carrier": "DHL"},
]

STATUSES = ("pending", "shipped", "cancelled")
