import os
from pathlib import Path

import nox

nox.options.stop_on_first_error = False
nox.options.reuse_existing_virtualenvs = True  # reuse between local runs; CI starts fresh

# ---------------------------------------------------------------------------
# Version matrix — drives integration tests only
# Unit tests don't depend on dbt at all (pure Jinja2 macro rendering)
# ---------------------------------------------------------------------------

DBT_MATRIX = [
    {
        "name": "dbt-core-1.9",
        "adapter": "dbt-bigquery~=1.9.0",
        "install_method": "pip",
        "pip_spec": "dbt-core~=1.9.0",
    },
    {
        "name": "dbt-core-latest",
        "adapter": "dbt-bigquery",
        "install_method": "pip",
        "pip_spec": "dbt-core",
    },
    {
        "name": "dbt-core-v2-preview",
        "adapter": "dbt-bigquery",
        "install_method": "pip",
        "pip_spec": "dbt-core>=2.0.0a0",
        "pip_flags": ["--pre"],  # installs the dbt-core v2 preview release
    },
    {
        "name": "dbt-core-v2-preview-fixed",
        "adapter": "dbt-bigquery",
        "install_method": "local",
        "pip_spec": None,
    },
    {
        "name": "dbt-fusion-latest",
        # dbt Fusion is a binary-only distribution, not on PyPI.
        # Installed via the official shell installer into ~/.local/bin/dbt.
        # Uses the native reservation config since it compiles using dbt v2 preview.
        "adapter": "dbt-bigquery",
        "install_method": "script",
        "pip_spec": None,
    },
    {
        "name": "dbt-fusion-latest-fixed",
        "adapter": "dbt-bigquery",
        "install_method": "local",
        "pip_spec": None,
    },
]

nox.options.sessions = ["unit"]  # default: run unit tests

DBT_FUSION_INSTALLER = "https://public.cdn.getdbt.com/fs/install/install.sh"


def _has_gcp_credentials() -> bool:
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return True
    adc_file = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    return adc_file.exists()


def _install_dbt(session: nox.Session, entry: dict) -> str:
    """Install dbt for the session and return the dbt executable path to use."""
    if entry["install_method"] == "pip":
        flags = entry.get("pip_flags", [])
        session.install(*flags, entry["pip_spec"], entry["adapter"])
        # dbt-core installs its own `dbt` script into the nox venv bin
        return "dbt"
    elif entry["install_method"] == "local":
        session.run(
            "bash", "-c",
            "cd /Users/maxostapenko/GitHub/dbt-core && cargo build --package dbt-sa-cli",
            external=True
        )
        return "/Users/maxostapenko/GitHub/dbt-core/target/debug/dbt-sa-cli"
    else:
        session.run(
            "bash", "-c",
            f"curl -fsSL {DBT_FUSION_INSTALLER} | sh -s -- --update",
            external=True,
        )
        # dbt-bigquery pulls in dbt-core as a transitive dep, which would shadow
        # the fusion binary in PATH (nox prepends the venv bin). Fusion bundles
        # its own BigQuery adapter, so we install nothing from pip and use the
        # absolute path to the fusion binary to avoid any PATH ambiguity.
        return str(Path.home() / ".local" / "bin" / "dbt")


# ---------------------------------------------------------------------------
# Unit tests — single session, no dbt dependency
# ---------------------------------------------------------------------------

@nox.session(python="3.12")
def unit(session: nox.Session) -> None:
    session.install("pytest", "jinja2", "pyyaml")
    session.run("pytest", "-v")


# ---------------------------------------------------------------------------
# Integration tests — one session per matrix entry
# ---------------------------------------------------------------------------

for _entry in DBT_MATRIX:
    def _make_integration(e=_entry):
        @nox.session(name=f"integration-{e['name']}", python="3.12")
        def _session(session: nox.Session) -> None:
            if not _has_gcp_credentials():
                session.skip(
                    "No GCP credentials found. Set GOOGLE_APPLICATION_CREDENTIALS or run "
                    "`gcloud auth application-default login` to enable integration tests."
                )
            session.install("pyyaml", "google-cloud-bigquery")
            dbt = _install_dbt(session, e)
            session.chdir("integration_tests")
            # Use a per-session target dir so each engine's output is isolated
            # and verification always inspects the current session's artifacts.
            # DBT_TARGET_PATH works for both dbt-core and dbt-fusion.
            target_path = f".target-{e['name']}"
            dbt_env = {"DBT_TARGET_PATH": target_path}
            if e["install_method"] == "local":
                dbt_env.update({
                    "DISABLE_CDN_DRIVER_CACHE": "true",
                    "ADBC_REPOSITORY": "/Users/maxostapenko/GitHub/arrow-adbc/go/adbc/pkg",
                })
            # dbt-fusion changed the package-lock.yml schema (error dbt1041).
            # Delete any stale lock file and packages so each engine regenerates them fresh.
            import shutil
            workspace_dir = Path(__file__).parent.resolve()
            integration_tests_dir = workspace_dir / "integration_tests"
            for clean_path in ("dbt_packages", "package-lock.yml"):
                p = integration_tests_dir / clean_path
                if p.is_symlink():
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p)
                elif p.exists():
                    p.unlink()

            seeds_dir = integration_tests_dir / "seeds"
            seeds_dir.mkdir(exist_ok=True)
            properties_yml = seeds_dir / "properties.yml"
            if "v2" in e["name"]:
                properties_content = """version: 2
seeds:
  - name: some_seed
    config:
      reservation: "{{ bq_reservations.get_name_from_config() }}"
"""
                properties_yml.write_text(properties_content)
            else:
                if properties_yml.exists():
                    properties_yml.unlink()

            def get_latest_invocation_id(target_dir: Path) -> str | None:
                run_results_path = target_dir / "run_results.json"
                if run_results_path.exists():
                    try:
                        import json
                        data = json.loads(run_results_path.read_text())
                        return data.get("metadata", {}).get("invocation_id")
                    except Exception:
                        pass
                return None

            invocation_ids = []
            target_dir_path = integration_tests_dir / target_path

            def run_dbt_cmd(cmd: str) -> None:
                run_results_path = target_dir_path / "run_results.json"
                if run_results_path.exists():
                    try:
                        run_results_path.unlink()
                    except Exception:
                        pass
                session.run(
                    dbt, "--warn-error", cmd,
                    external=True, env=dbt_env
                )
                inv_id = get_latest_invocation_id(target_dir_path)
                if inv_id and inv_id not in invocation_ids:
                    invocation_ids.append(inv_id)

            try:
                session.run(dbt, "--warn-error", "deps", external=True, env=dbt_env)
                run_dbt_cmd("build")

                verify_args = [
                    "python", "../scripts/verify_integration.py",
                    "--target-path", target_path,
                    "--dbt-version-name", e["name"],
                    "--results-markdown", "../verification_results.md",
                ]
                if invocation_ids:
                    verify_args.extend(["--invocation-ids", ",".join(invocation_ids)])
                session.run(*verify_args)
            finally:
                if properties_yml.exists():
                    properties_yml.unlink()

    _make_integration()
