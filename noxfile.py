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
        "pip_spec": "dbt-core",
        "pip_flags": ["--pre"],  # installs the dbt-core v2 preview release
    },
    {
        "name": "dbt-fusion-latest",
        # dbt Fusion is a binary-only distribution, not on PyPI.
        # Installed via the official shell installer into ~/.local/bin/dbt.
        # NOTE: dbt-fusion preview does not support sql_header — this session
        # is expected to fail until fusion adds sql_header support.
        "adapter": "dbt-bigquery",
        "install_method": "script",
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

TAG_MAPPING = {
    "dbt-core-1.9": "dbt_core_v1",
    "dbt-core-latest": "dbt_core_latest",
    "dbt-core-v2-preview": "dbt_core_v2",
    "dbt-fusion-latest": "dbt_core_fusion_latest",
}


for _entry in DBT_MATRIX:
    def _make_integration(e=_entry):
        @nox.session(name=f"integration-{e['name']}", python="3.12")
        def _session(session: nox.Session) -> None:
            if not _has_gcp_credentials():
                session.skip(
                    "No GCP credentials found. Set GOOGLE_APPLICATION_CREDENTIALS or run "
                    "`gcloud auth application-default login` to enable integration tests."
                )
            dbt = _install_dbt(session, e)
            session.chdir("integration_tests")
            # Use a per-session target dir so each engine's output is isolated
            # and verification always inspects the current session's artifacts.
            # DBT_TARGET_PATH works for both dbt-core and dbt-fusion.
            target_path = f".target-{e['name']}"
            dbt_env = {"DBT_TARGET_PATH": target_path}
            # dbt-fusion changed the package-lock.yml schema (error dbt1041).
            # Delete any stale lock file so each engine regenerates it fresh.
            lock_file = Path("package-lock.yml")
            if lock_file.exists():
                lock_file.unlink()
            session.run(dbt, "--warn-error", "deps", external=True)
            
            tag = TAG_MAPPING[e["name"]]
            session.run(
                dbt, "--warn-error", "compile", 
                "--select", f"tag:{tag}", 
                external=True, env=dbt_env
            )
            session.run(
                dbt, "--warn-error", "run", 
                "--select", f"tag:{tag}", 
                external=True, env=dbt_env
            )
            session.run(
                "python", "../scripts/verify_integration.py",
                "--target-path", target_path,
                "--tag", tag,
            )

    _make_integration()
