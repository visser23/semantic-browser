# Versioning

Semantic Browser uses [Semantic Versioning](https://semver.org/) (SemVer).

## Current version

**1.3.2** — consistent across `pyproject.toml`, `semantic_browser.__version__`, and README.

## Version sources

The version is defined in exactly two places. Both must match on every release:

| File | Field |
|------|-------|
| `pyproject.toml` | `version = "X.Y.Z"` |
| `src/semantic_browser/__init__.py` | `__version__ = "X.Y.Z"` |

The README references the current version in the header line. The CHANGELOG records the history.

## Increment rules

| Change type | Bump | Example |
|-------------|------|---------|
| Breaking API change | Major (X) | Removing a public method, changing return types |
| New feature, backward-compatible | Minor (Y) | New observation mode, new CLI command |
| Bug fix, docs, version alignment | Patch (Z) | Fix version mismatch, doc improvements |

## Release checklist

1. Update version in `pyproject.toml` and `__init__.py` (both must match).
2. Add a CHANGELOG entry for the new version.
3. Ensure README version header matches.
4. Tag the release in git: `git tag v1.3.2`
5. Build and publish to PyPI (see `docs/publishing.md`).
6. Verify: `pip install semantic-browser==1.3.2 && semantic-browser version`

## Helper script

```bash
python tools/next_version.py
```

Prints the current version state and commit count for reference.
