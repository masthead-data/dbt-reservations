import json
import subprocess
from pathlib import Path


def test_3tier_centralized_integration_project():
    project_dir = Path(__file__).parent.parent / "integration_tests_centralized"
    manifest_path = project_dir / "target" / "manifest.json"

    # 1. Run dbt deps
    subprocess.run(
        ["dbt", "deps"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    )

    # 2. Run dbt compile
    subprocess.run(
        ["dbt", "compile"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    )

    assert manifest_path.exists(), f"manifest.json not found at {manifest_path}"

    with open(manifest_path) as f:
        manifest = json.load(f)

    nodes = manifest.get("nodes", {})

    def get_reservation_value(node):
        cfg = node.get("config", {})
        # Check native reservation property (dbt v2+) or sql_header (dbt v1)
        res = cfg.get("reservation")
        if res is not None:
            return res
        sql_header = cfg.get("sql_header", "")
        if "SET @@reservation=" in sql_header:
            return sql_header.split('SET @@reservation=')[-1].strip().strip('";')
        return None

    # Check model 1: Central reservation assignment
    central_node = nodes.get("model.centralized_integration_test.central_model")
    assert central_node is not None, "central_model node missing from manifest"
    assert get_reservation_value(central_node) == "projects/masthead-dev/locations/us/reservations/central-capacity"

    # Check model 2: Central on-demand assignment
    on_demand_node = nodes.get("model.centralized_integration_test.central_on_demand_model")
    assert on_demand_node is not None, "central_on_demand_model node missing from manifest"
    assert get_reservation_value(on_demand_node) == "none"

    # Check model 3: Local fallback assignment
    fallback_node = nodes.get("model.centralized_integration_test.local_fallback_model")
    assert fallback_node is not None, "local_fallback_model node missing from manifest"
    assert get_reservation_value(fallback_node) == "projects/masthead-dev/locations/us/reservations/local-capacity"
