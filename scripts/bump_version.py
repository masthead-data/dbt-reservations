#!/usr/bin/env python3
"""Bump the version in dbt_project.yml and package_manifest.json, and commit.

Usage:
  python scripts/bump_version.py [new_version]

Examples:
  python scripts/bump_version.py 0.1.1
"""
import json
import subprocess
import sys
from pathlib import Path

import yaml


def read_json(path: Path):
    return json.loads(path.read_text())


def write_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def bump_dbt_project_version(path: Path, new_version: str):
    data = yaml.safe_load(path.read_text())
    data['version'] = str(new_version)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def main():
    if len(sys.argv) < 2:
        print("Usage: bump_version.py NEW_VERSION")
        sys.exit(2)
    new_version = sys.argv[1]

    root = Path(__file__).resolve().parents[1]
    dbt_yml = root / 'dbt_project.yml'
    manifest = root / 'package_manifest.json'

    print(f"Bumping version to {new_version}...")
    bump_dbt_project_version(dbt_yml, new_version)

    files_to_add = [str(dbt_yml)]
    if manifest.exists():
        data = read_json(manifest)
        data['version'] = str(new_version)
        write_json(manifest, data)
        files_to_add.append(str(manifest))

    subprocess.check_call(['git', 'add'] + files_to_add)
    subprocess.check_call(['git', 'commit', '-m', f'Release {new_version}'])


if __name__ == '__main__':
    main()
