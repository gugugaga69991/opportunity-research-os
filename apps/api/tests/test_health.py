from fastapi.testclient import TestClient

from opportunity_api.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_dashboard_origin_is_allowed() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_collection_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])
    assert "/collection/sources" in paths
    assert "/collection/sources/{source_id}/runs" in paths
    assert "/collection/webhooks/apify/{secret}" in paths


def test_processing_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])
    assert "/processing/backfill" in paths
    assert "/processing/signals" in paths
    assert "/processing/signals/{signal_id}" in paths
    assert "/processing/metrics" in paths


def test_intelligence_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])
    assert "/intelligence/backfill" in paths
    assert "/intelligence/clusters" in paths
    assert "/intelligence/clusters/{cluster_id}" in paths
    assert "/intelligence/entities" in paths
    assert "/intelligence/relationships" in paths
    assert "/intelligence/metrics" in paths


def test_opportunity_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])
    assert "/opportunities" in paths
    assert "/opportunities/generate/backfill" in paths
    assert "/opportunities/clusters/{cluster_id}/generate" in paths
    assert "/opportunities/{opportunity_id}" in paths
    assert "/opportunities/{opportunity_id}/state" in paths
    assert "/opportunities/{opportunity_id}/refresh" in paths
    assert "/opportunities/metrics" in paths


def test_validation_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])
    assert "/validation/decisions/{decision_id}/campaigns" in paths
    assert "/validation/campaigns" in paths
    assert "/validation/campaigns/{campaign_id}" in paths
    assert "/validation/experiments/{experiment_id}/results" in paths
    assert "/validation/metrics" in paths


def test_learning_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])
    assert "/learning/opportunities/{opportunity_id}/outcomes" in paths
    assert "/learning/calibration/runs" in paths
    assert "/learning/calibration/runs/{run_id}/review" in paths
    assert "/learning/freshness" in paths
    assert "/learning/freshness/{assessment_id}/refresh" in paths
    assert "/learning/metrics" in paths


def test_operator_handoff_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])
    assert "/operations/portfolio/sync" in paths
    assert "/operations/alerts" in paths
    assert "/operations/opportunities/{opportunity_id}/interviews" in paths
    assert "/operations/opportunities/{opportunity_id}/build-spec" in paths
    assert "/operations/build-specs/{spec_id}/review" in paths
    assert "/operations/metrics" in paths
