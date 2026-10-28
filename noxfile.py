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
    # dbt-core v1 — sql_header is the only mechanism.
    {
        "name": "dbt-core-latest",
        "install_method": "pip",
        "pip_spec": ["dbt-core", "dbt-bigquery"],
        "reservation_method": "sql_header",
    },
    # dbt v2 GA ships on PyPI as `dbt` (the `dbt-core` 2.x line stopped at 2.0.0rc9) and bundles
    # BigQuery, so no adapter package. 2.0.8+ are cut from the `2.0.latest` branch, which pins
    # BigQuery ADBC driver dbt0.21.19 (no reservation option) — native config is ignored there.
    {
        "name": "dbt-v2-native",
        "install_method": "pip",
        "pip_spec": ["dbt"],
        "reservation_method": "native",
    },
    # Workaround candidate for released v2: SET @@reservation via sql_header, bypassing the driver.
    {
        "name": "dbt-v2-sql-header",
        "install_method": "pip",
        "pip_spec": ["dbt"],
        "reservation_method": "sql_header",
    },
    # CDN-only build (never published to PyPI) that shipped driver dbt0.21.20 with the reservation option.
    {
        "name": "dbt-v2.0.7-native",
        "install_method": "cdn",
        "cdn_version": "2.0.7",
        "reservation_method": "native",
    },
    # Nightly build from `main`: newer driver plus the adapter-side QUERY_RESERVATION wiring.
    {
        "name": "dbt-v2-nightly-native",
        "install_method": "cdn",
        "cdn_version": "nightly",
        "reservation_method": "native",
    },
]

DBT_CDN_URL = "https://public.cdn.getdbt.com/fs"

nox.options.sessions = ["unit"]  # default: run unit tests


def _has_gcp_credentials() -> bool:
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return True
    adc_file = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    return adc_file.exists()


def _cdn_target() -> str:
    import platform

    machine = platform.machine().lower()
    arch = "aarch64" if machine in ("arm64", "aarch64") else "x86_64"
    os_suffix = "apple-darwin" if platform.system() == "Darwin" else "unknown-linux-gnu"
    return f"{arch}-{os_suffix}"


def _resolve_cdn_version(version: str) -> str:
    """Resolve a CDN channel name (stable, nightly, ...) to a concrete version."""
    import json
    import urllib.request

    if version[0].isdigit():
        return version
    with urllib.request.urlopen(f"{DBT_CDN_URL}/versions.json") as resp:
        channels = json.load(resp)
    return channels[version]["tag"].lstrip("v")


def _install_dbt(session: nox.Session, entry: dict) -> str:
    """Install dbt for the session and return the dbt executable path to use."""
    if entry["install_method"] == "pip":
        flags = list(entry.get("pip_flags", []))
        # The `dbt` v2 sdist downloads its platform wheel with urllib at build time, which fails
        # on Python builds without a system CA bundle — point it at the venv's certifi bundle.
        session.install("certifi")
        session.env["SSL_CERT_FILE"] = session.run(
            "python", "-c", "import certifi; print(certifi.where())", silent=True
        ).strip()
        session.install(*flags, *entry["pip_spec"])
        # dbt installs its own `dbt` script into the nox venv bin
        return "dbt"
    elif entry["install_method"] == "cdn":
        version = _resolve_cdn_version(entry["cdn_version"])
        dest = (Path(session.cache_dir) / "dbt-cdn" / version).resolve()
        dbt = dest / "dbt"
        if not dbt.exists():
            dest.mkdir(parents=True, exist_ok=True)
            url = f"{DBT_CDN_URL}/cli/fs-v{version}-{_cdn_target()}.tar.gz"
            session.run(
                "bash", "-c", f'set -euo pipefail; curl -fsSL "{url}" | tar xz -C "{dest}"',
                external=True,
            )
        session.log(f"Using dbt {version} from {dbt}")
        return str(dbt)
    else:
        raise ValueError(f"Unknown install_method: {entry['install_method']}")


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
            target_path = f".target-{e['name']}"
            dbt_env = {"DBT_TARGET_PATH": target_path}
            method = e["reservation_method"]
            vars_arg = ["--vars", f"{{reservation_method: {method}}}"]
            # Delete any stale lock file, packages, and target so each engine regenerates them fresh.
            import shutil
            workspace_dir = Path(__file__).parent.resolve()
            integration_tests_dir = workspace_dir / "integration_tests"
            for clean_path in ("dbt_packages", "package-lock.yml", target_path):
                p = integration_tests_dir / clean_path
                if p.is_symlink():
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p)
                elif p.exists():
                    p.unlink()

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
                    dbt, "--warn-error", *cmd.split(), *vars_arg,
                    external=True, env=dbt_env
                )
                inv_id = get_latest_invocation_id(target_dir_path)
                if inv_id and inv_id not in invocation_ids:
                    invocation_ids.append(inv_id)

            session.run(dbt, "--warn-error", "deps", external=True, env=dbt_env)
            run_dbt_cmd("build --full-refresh")

            verify_args = [
                "python", "../scripts/verify_integration.py",
                "--target-path", target_path,
                "--dbt-version-name", e["name"],
                "--reservation-method", method,
                "--results-markdown", "../verification_results.md",
            ]
            if invocation_ids:
                verify_args.extend(["--invocation-ids", ",".join(invocation_ids)])
            session.run(*verify_args)

    _make_integration()
