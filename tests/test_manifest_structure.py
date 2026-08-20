import json
from pathlib import Path

def test_manifest_node_configurations():
    """Verify manifest nodes contain expected reservations when target/manifest.json is present."""
    manifest_path = Path(__file__).parent.parent / "integration_tests" / "target" / "manifest.json"
    if not manifest_path.exists():
        return  # skipped when integration_tests has not been compiled yet

    data = json.loads(manifest_path.read_text())
    nodes = data.get("nodes", {})

    expected_manifest_headers = {
        "model.bq_reservations_test.slots": "projects/masthead-dev/locations/us/reservations/capacity-1",
        "model.bq_reservations_test.slots_incremental": "projects/masthead-dev/locations/us/reservations/capacity-1",
        "model.bq_reservations_test.slots_materialized_view": "projects/masthead-dev/locations/us/reservations/enterprise-0",
        "model.bq_reservations_test.slots_ephemeral": "projects/masthead-dev/locations/us/reservations/capacity-1",
        "model.bq_reservations_test.slots_hooks": "projects/masthead-dev/locations/us/reservations/capacity-1",
        "model.bq_reservations_test.slots_path": "projects/masthead-dev/locations/us/reservations/capacity-1",
        "model.bq_reservations_test.slots_path_incremental": "projects/masthead-dev/locations/us/reservations/capacity-1",
        "model.bq_reservations_test.on_demand": "SET @@reservation= \"none\";",
        "snapshot.bq_reservations_test.slots_snapshot": "projects/masthead-dev/locations/us/reservations/capacity-1",
    }

    for node_id, expected_val in expected_manifest_headers.items():
        node = nodes.get(node_id)
        assert node is not None, f"Node {node_id} not found in manifest"
        config = node.get("config", {})
        sql_header = config.get("sql_header") or ""
        native_res = config.get("reservation") or ""
        # On dbt v1, sql_header is populated; on dbt v2, reservation or sql_header is populated
        matched = (expected_val in sql_header) or (expected_val in native_res) or (expected_val == "SET @@reservation= \"none\";" and (expected_val in sql_header or native_res == "none"))
        assert matched, f"{node_id} expected {expected_val!r} in sql_header or reservation, got sql_header={sql_header!r}, reservation={native_res!r}"

    # Verify default model has empty sql_header / null reservation
    default_node = nodes.get("model.bq_reservations_test.default")
    assert default_node is not None
    assert not default_node.get("config", {}).get("sql_header")
