#!/usr/bin/env python3
"""Bump the version in dbt_project.yml and package_manifest.json, commit and tag.

Usage:
  python scripts/bump_version.py [new_version] [--tag]

Examples:
  python scripts/bump_version.py 0.1.1 --tag
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
        print("Usage: bump_version.py NEW_VERSION [--tag]")
        sys.exit(2)
    new_version = sys.argv[1]
    create_tag = '--tag' in sys.argv

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
    subprocess.check_call(['git', 'commit', '-m', f'Release v{new_version}'])

    if create_tag:
        tag_name = new_version
        subprocess.check_call(['git', 'tag', '-a', tag_name, '-m', tag_name])
        print(f"Created tag {tag_name}. Don't forget to push: git push origin main --tags")


if __name__ == '__main__':
    main()
