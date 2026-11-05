"""
Tests for reports API endpoints.
"""
import pytest


class TestReportsEndpoints:
    """Test suite for /api/reports/* endpoints."""

    def test_get_quarterly_reports(self, client):
        """Test getting quarterly reports without filters."""
        response = client.get("/api/reports/quarterly")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        for quarter in data:
            assert "quarter" in quarter
            assert "total_orders" in quarter
            assert "total_revenue" in quarter
            assert "avg_order_value" in quarter
            assert "fulfillment_rate" in quarter
            assert 0 <= quarter["fulfillment_rate"] <= 100

    def test_get_monthly_trends(self, client):
        """Test getting monthly trends without filters."""
        response = client.get("/api/reports/monthly-trends")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        for month in data:
            assert "month" in month
            assert "order_count" in month
            assert "revenue" in month

        # Results must be sorted chronologically
        months = [m["month"] for m in data]
        assert months == sorted(months)

    def test_quarterly_totals_match_orders(self, client):
        """Quarterly order counts should add up to the orders in the quarters."""
        orders = client.get("/api/orders").json()
        quarterly = client.get("/api/reports/quarterly").json()

        assert sum(q["total_orders"] for q in quarterly) == len(orders)
        revenue = sum(o["total_value"] for o in orders)
        assert abs(sum(q["total_revenue"] for q in quarterly) - revenue) < 0.01

    def test_monthly_trends_filtered_by_warehouse(self, client):
        """Warehouse filter should match the filtered orders endpoint."""
        orders = client.get("/api/orders?warehouse=Tokyo").json()
        trends = client.get("/api/reports/monthly-trends?warehouse=Tokyo").json()

        assert sum(m["order_count"] for m in trends) == len(orders)
        assert abs(sum(m["revenue"] for m in trends) - sum(o["total_value"] for o in orders)) < 0.01

    def test_quarterly_filtered_by_status(self, client):
        """Status filter should only count orders of that status."""
        orders = client.get("/api/orders?status=Delivered").json()
        quarterly = client.get("/api/reports/quarterly?status=Delivered").json()

        assert sum(q["total_orders"] for q in quarterly) == len(orders)
        for quarter in quarterly:
            assert quarter["fulfillment_rate"] == 100

    def test_monthly_trends_filtered_by_quarter(self, client):
        """Quarter filter should restrict results to the quarter's months."""
        trends = client.get("/api/reports/monthly-trends?month=Q1-2025").json()

        for month in trends:
            assert month["month"] in ["2025-01", "2025-02", "2025-03"]

    def test_quarterly_filtered_by_month(self, client):
        """Single month filter should return only the quarter containing it."""
        quarterly = client.get("/api/reports/quarterly?month=2025-01").json()

        assert all(q["quarter"] == "Q1-2025" for q in quarterly)

    def test_reports_multiple_filters(self, client):
        """Combined filters should match the filtered orders endpoint."""
        query = "warehouse=London&category=Sensors&status=Delivered"
        orders = client.get(f"/api/orders?{query}").json()
        quarterly = client.get(f"/api/reports/quarterly?{query}").json()
        trends = client.get(f"/api/reports/monthly-trends?{query}").json()

        assert sum(q["total_orders"] for q in quarterly) == len(orders)
        assert sum(m["order_count"] for m in trends) == len(orders)

    def test_reports_all_filter_values_ignored(self, client):
        """'all' filter values should behave like no filter."""
        unfiltered = client.get("/api/reports/quarterly").json()
        with_all = client.get(
            "/api/reports/quarterly?warehouse=all&category=all&status=all&month=all"
        ).json()

        assert unfiltered == with_all
