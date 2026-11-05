"""
Tests for restocking API endpoints.
"""
import pytest

import main


@pytest.fixture(autouse=True)
def reset_submitted_orders():
    """Submitted orders are module-level in-memory state; isolate each test."""
    main.submitted_orders.clear()
    yield
    main.submitted_orders.clear()


class TestRestockRecommendations:
    """Test suite for the recommendations endpoint."""

    def test_zero_budget_returns_no_items(self, client):
        response = client.get("/api/restocking/recommendations?budget=0")
        assert response.status_code == 200

        data = response.json()
        assert data["items"] == []
        assert data["total_cost"] == 0
        assert data["remaining_budget"] == 0

    def test_negative_budget_rejected(self, client):
        response = client.get("/api/restocking/recommendations?budget=-5")
        assert response.status_code == 400

    def test_huge_budget_covers_every_shortfall(self, client):
        data = client.get("/api/restocking/recommendations?budget=10000000").json()
        assert len(data["items"]) > 0

        for item in data["items"]:
            assert item["shortfall"] > 0
            # With ample budget each item is restocked to cover its full shortfall
            assert item["recommended_qty"] == item["shortfall"]
            assert item["forecasted_demand"] - item["quantity_on_hand"] == item["shortfall"]
            assert item["lead_time_days"] > 0

    def test_items_sorted_by_shortfall_descending(self, client):
        data = client.get("/api/restocking/recommendations?budget=10000000").json()
        shortfalls = [i["shortfall"] for i in data["items"]]
        assert shortfalls == sorted(shortfalls, reverse=True)

    def test_total_never_exceeds_budget(self, client):
        for budget in (50, 500, 2500, 10000):
            data = client.get(f"/api/restocking/recommendations?budget={budget}").json()
            assert data["total_cost"] <= budget
            assert abs(data["total_cost"] + data["remaining_budget"] - budget) < 0.01
            line_sum = sum(i["line_cost"] for i in data["items"])
            assert abs(line_sum - data["total_cost"]) < 0.01

    def test_small_budget_gives_partial_quantity(self, client):
        full = client.get("/api/restocking/recommendations?budget=10000000").json()
        top = full["items"][0]
        # Budget for roughly half of the top item's shortfall
        budget = top["unit_cost"] * (top["shortfall"] // 2)

        data = client.get(f"/api/restocking/recommendations?budget={budget}").json()
        assert data["items"][0]["sku"] == top["sku"]
        assert data["items"][0]["recommended_qty"] < top["shortfall"]


class TestRestockOrders:
    """Test suite for submitting and listing restock orders."""

    def _first_recommendation(self, client):
        return client.get("/api/restocking/recommendations?budget=10000000").json()["items"][0]

    def test_submit_order_success(self, client):
        rec = self._first_recommendation(client)
        payload = {"budget": 10000000, "items": [{"sku": rec["sku"], "quantity": 2}]}

        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 201

        order = response.json()
        assert order["order_number"].startswith("RST-")
        assert order["status"] == "Submitted"
        assert order["lead_time_days"] == rec["lead_time_days"]
        assert abs(order["total_cost"] - 2 * rec["unit_cost"]) < 0.01
        assert len(order["items"]) == 1

    def test_order_lead_time_is_longest_item(self, client):
        recs = client.get("/api/restocking/recommendations?budget=10000000").json()["items"]
        assert len(recs) >= 2
        payload = {
            "budget": 10000000,
            "items": [{"sku": r["sku"], "quantity": 1} for r in recs],
        }
        order = client.post("/api/restocking/orders", json=payload).json()
        assert order["lead_time_days"] == max(r["lead_time_days"] for r in recs)

    def test_submitted_order_listed_newest_first(self, client):
        rec = self._first_recommendation(client)
        payload = {"budget": 10000000, "items": [{"sku": rec["sku"], "quantity": 1}]}
        first = client.post("/api/restocking/orders", json=payload).json()
        second = client.post("/api/restocking/orders", json=payload).json()

        listed = client.get("/api/restocking/orders").json()
        assert [o["id"] for o in listed] == [second["id"], first["id"]]

    def test_empty_order_rejected(self, client):
        response = client.post("/api/restocking/orders", json={"budget": 100, "items": []})
        assert response.status_code == 400

    def test_unknown_sku_rejected(self, client):
        payload = {"budget": 100, "items": [{"sku": "NOPE-000", "quantity": 1}]}
        assert client.post("/api/restocking/orders", json=payload).status_code == 400

    def test_non_positive_quantity_rejected(self, client):
        rec = self._first_recommendation(client)
        payload = {"budget": 10000000, "items": [{"sku": rec["sku"], "quantity": 0}]}
        assert client.post("/api/restocking/orders", json=payload).status_code == 400

    def test_duplicate_sku_rejected(self, client):
        rec = self._first_recommendation(client)
        line = {"sku": rec["sku"], "quantity": 1}
        payload = {"budget": 10000000, "items": [line, line]}
        assert client.post("/api/restocking/orders", json=payload).status_code == 400

    def test_order_over_budget_rejected(self, client):
        rec = self._first_recommendation(client)
        # Budget deliberately below the server-computed cost of a single unit
        payload = {"budget": rec["unit_cost"] / 2, "items": [{"sku": rec["sku"], "quantity": 1}]}
        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 400
        assert "budget" in response.json()["detail"].lower()
        assert client.get("/api/restocking/orders").json() == []
