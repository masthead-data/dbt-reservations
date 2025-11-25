#!/usr/bin/env python3
"""Bump the version in dbt_project.yml and commit.

Usage:
  python scripts/bump_version.py [new_version]

Examples:
  python scripts/bump_version.py 0.1.1
"""
import subprocess
import sys
from pathlib import Path

import yaml


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

    print(f"Bumping version to {new_version}...")
    bump_dbt_project_version(dbt_yml, new_version)

    subprocess.check_call(['git', 'add', str(dbt_yml)])
    subprocess.check_call(['git', 'commit', '-m', f'Release v{new_version}'])


if __name__ == '__main__':
    main()
