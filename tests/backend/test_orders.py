"""
Tests for the Orders creation (restocking) API endpoint.
"""
import re
from datetime import datetime

import pytest


class TestCreateOrderEndpoint:
    """Test suite for POST /api/orders (internal restock orders)."""

    def _valid_payload(self):
        return {
            "items": [
                {"sku": "PCB-001", "name": "Single Layer PCB Assembly", "quantity": 100, "unit_price": 24.99},
                {"sku": "TMP-201", "name": "Temperature Sensor", "quantity": 50, "unit_price": 89.5},
            ],
            "budget": 50000,
            "warehouse": "all",
            "category": "all",
        }

    def test_create_order_success(self, client):
        """A valid restock order is created and returned with 201."""
        payload = self._valid_payload()
        response = client.post("/api/orders", json=payload)
        assert response.status_code == 201

        order = response.json()
        assert order["is_restock"] is True
        assert order["status"] == "Processing"
        assert order["customer"] == "Internal Restock"
        assert re.match(r"^ORD-2025-\d{4}$", order["order_number"])

        # total_value equals sum(quantity * unit_price)
        expected_total = sum(i["quantity"] * i["unit_price"] for i in payload["items"])
        assert abs(order["total_value"] - expected_total) < 0.01

        # expected_delivery is 14 days after order_date (fixed lead time)
        order_date = datetime.strptime(order["order_date"], "%Y-%m-%dT%H:%M:%S")
        expected_delivery = datetime.strptime(order["expected_delivery"], "%Y-%m-%dT%H:%M:%S")
        assert (expected_delivery - order_date).days == 14

    def test_create_order_normalizes_all_filters(self, client):
        """'all' warehouse/category are stored as null, not the literal 'all'."""
        response = client.post("/api/orders", json=self._valid_payload())
        assert response.status_code == 201
        order = response.json()
        assert order["warehouse"] is None
        assert order["category"] is None

    def test_create_order_appears_in_get(self, client):
        """A created order is retrievable via GET /api/orders."""
        created = client.post("/api/orders", json=self._valid_payload()).json()
        order_number = created["order_number"]

        all_orders = client.get("/api/orders").json()
        match = next((o for o in all_orders if o["order_number"] == order_number), None)
        assert match is not None
        assert match["is_restock"] is True

    def test_create_order_empty_items(self, client):
        """An order with no items returns 400."""
        payload = self._valid_payload()
        payload["items"] = []
        response = client.post("/api/orders", json=payload)
        assert response.status_code == 400
        assert "detail" in response.json()

    def test_create_order_missing_items(self, client):
        """A request missing the required 'items' field returns 422."""
        response = client.post("/api/orders", json={"budget": 1000})
        assert response.status_code == 422

    def test_create_order_non_positive_quantity(self, client):
        """An item with zero or negative quantity returns 400."""
        payload = self._valid_payload()
        payload["items"][0]["quantity"] = 0
        response = client.post("/api/orders", json=payload)
        assert response.status_code == 400

    def test_existing_orders_have_is_restock_false(self, client):
        """Seed orders serialize is_restock as False (Optional default, no migration)."""
        all_orders = client.get("/api/orders").json()
        assert len(all_orders) > 0
        # The very first seed orders should not be restock orders
        seed_orders = [o for o in all_orders if o["order_number"] == "ORD-2025-0001"]
        assert len(seed_orders) == 1
        assert seed_orders[0]["is_restock"] is False
