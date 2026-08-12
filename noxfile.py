import os
import sys
from pathlib import Path
import nox

# Matrix of dbt versions to test against
DBT_MATRIX = [
    {
        "name": "dbt-core-1.9",
        "install_method": "pip",
        "pip_spec": "dbt-core~=1.9.0",
        "adapter": "dbt-bigquery",
    },
    {
        "name": "dbt-core-latest",
        "install_method": "pip",
        "pip_spec": "dbt-core",
        "adapter": "dbt-bigquery",
    },
    {
        "name": "dbt-core-v2-preview",
        "install_method": "pip_pre",
        "pip_spec": "dbt-core>=2.0.0a0",
        "adapter": "dbt-bigquery",
    },
    {
        "name": "dbt-core-v2-preview-fixed",
        "install_method": "local",
        "pip_spec": "",
        "adapter": "",
    },
    {
        "name": "dbt-fusion-latest",
        "install_method": "fusion",
        "pip_spec": "",
        "adapter": "",
    },
    {
        "name": "dbt-fusion-latest-fixed",
        "install_method": "fusion_local",
        "pip_spec": "",
        "adapter": "",
    },
]

REPOS = {
    "dbt-core": {
        "url": "https://github.com/max-ostapenko/dbt-core.git",
        "branch": "feature/bigquery-reservation",
    },
    "dbt-fusion": {
        "url": "https://github.com/max-ostapenko/dbt-fusion.git",
        "branch": "feature/bigquery-reservation",
    },
    "arrow-adbc": {
        "url": "https://github.com/max-ostapenko/arrow-adbc.git",
        "branch": "feat--bigquery-reservation",
    },
}

REBUILD_FIXED = os.environ.get("REBUILD", "false").lower() in ("true", "1", "yes")

nox.options.sessions = ["unit"]  # default: run unit tests


def _has_gcp_credentials() -> bool:
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return True
    adc_path = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    return adc_path.exists()


def _ensure_git_repo(session: nox.Session, repo_key: str) -> tuple[Path, bool]:
    info = REPOS[repo_key]
    deps_dir = Path(__file__).parent.resolve() / ".deps"
    deps_dir.mkdir(exist_ok=True)
    target_dir = deps_dir / repo_key
    updated = False

    if not (target_dir / ".git").exists():
        session.run("git", "clone", "-b", info["branch"], info["url"], str(target_dir), external=True)
        updated = True
    else:
        old_head = session.run("git", "-C", str(target_dir), "rev-parse", "HEAD", external=True, silent=True).strip()
        session.run("git", "-C", str(target_dir), "fetch", "origin", info["branch"], external=True)
        session.run("git", "-C", str(target_dir), "checkout", info["branch"], external=True)
        session.run("git", "-C", str(target_dir), "reset", "--hard", f"origin/{info['branch']}", external=True)
        new_head = session.run("git", "-C", str(target_dir), "rev-parse", "HEAD", external=True, silent=True).strip()
        if old_head != new_head:
            updated = True

    return target_dir, updated


def _install_dbt(session: nox.Session, entry: dict) -> str:
    """Install dbt for the session and return the dbt executable path to use."""
    if entry["install_method"] == "pip":
        session.install(entry["pip_spec"], entry["adapter"])
        return "dbt"
    elif entry["install_method"] == "pip_pre":
        flags = ["--pre"]
        session.install(*flags, entry["pip_spec"], entry["adapter"])
        return "dbt"
    elif entry["install_method"] in ("local", "fusion_local"):
        repo_key = "dbt-core" if entry["install_method"] == "local" else "dbt-fusion"
        dbt_repo_dir, repo_updated = _ensure_git_repo(session, repo_key)
        _ensure_git_repo(session, "arrow-adbc")

        fusion_bin = None
        for b_name in ("dbt-sa-cli", "dbt"):
            candidate = dbt_repo_dir / "target" / "release" / b_name
            if candidate.exists():
                fusion_bin = candidate
                break

        if fusion_bin is None or repo_updated or REBUILD_FIXED:
            session.chdir(dbt_repo_dir)
            session.run("cargo", "build", "--release", external=True)
            for b_name in ("dbt-sa-cli", "dbt"):
                candidate = dbt_repo_dir / "target" / "release" / b_name
                if candidate.exists():
                    fusion_bin = candidate
                    break

        return str(fusion_bin)
    elif entry["install_method"] == "fusion":
        session.run(
            "bash", "-c",
            "curl -fsSL https://public.cdn.getdbt.com/fs/install/install.sh | sh -s -- --update",
            external=True,
        )
        fusion_bin = Path.home() / ".local" / "bin" / "dbt"
        return str(fusion_bin)
    else:
        raise ValueError(f"Unknown install method: {entry['install_method']}")


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
            workspace_dir = Path(__file__).parent.resolve()
            integration_tests_dir = workspace_dir / "integration_tests"
            centralized_tests_dir = workspace_dir / "integration_tests_centralized"

            session.chdir(integration_tests_dir)
            target_path = f".target-{e['name']}"
            dbt_env = {"DBT_TARGET_PATH": target_path}
            if "fixed" in e["name"]:
                adbc_pkg_dir = workspace_dir / ".deps" / "arrow-adbc" / "go" / "adbc" / "pkg"
                dbt_env.update({
                    "DISABLE_CDN_DRIVER_CACHE": "true",
                    "ADBC_REPOSITORY": str(adbc_pkg_dir),
                })
            
            import shutil
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

                # Execute centralized project test suite
                session.chdir(centralized_tests_dir)
                session.run(dbt, "--warn-error", "deps", external=True)
                session.run(dbt, "--warn-error", "run", external=True)
            finally:
                if properties_yml.exists():
                    properties_yml.unlink()

    _make_integration()
