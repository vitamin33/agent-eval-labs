"""Deterministic fixture data for the orderdesk environment.

Plain literals, no generation: the state must be identical on every machine and
every run, because every ground-truth assert in this experiment is computed
from it.
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

# O13 belongs to C9, who does not exist: the orphan T3 has to find.
ORDERS = [
    {"id": "O01", "customer_id": "C1", "total": 120.00, "status": "pending"},
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
    {"id": "O13", "customer_id": "C9", "total": 88.00,  "status": "pending"},
]

# Shipment records are the independent route to a status: T5 finds orders whose
# status contradicts them. O02 is marked shipped with no shipment record.
SHIPMENTS = [
    {"order_id": "O06", "carrier": "DHL"},
    {"order_id": "O08", "carrier": "UPS"},
    {"order_id": "O12", "carrier": "DHL"},
]

STATUSES = ("pending", "shipped", "cancelled")
