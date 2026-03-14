#!/usr/bin/env bash
# Usage: ./scripts/release.sh 1.2.0
# Bumps manifest.json, commits, tags, and pushes — all in sync.

set -euo pipefail

MANIFEST="custom_components/baillconnect/manifest.json"

# ── Argument check ────────────────────────────────────────────────────────────
if [ $# -ne 1 ]; then
  echo "Usage: $0 <version>  (e.g. $0 1.2.0)"
  exit 1
fi

NEW_VERSION="$1"

# Basic semver format check
if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Error: version must follow semver format (e.g. 1.2.0)"
  exit 1
fi

TAG="v${NEW_VERSION}"

# ── Working tree must be clean ────────────────────────────────────────────────
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Error: working tree is not clean. Commit or stash your changes first."
  exit 1
fi

# ── Tag must not already exist ────────────────────────────────────────────────
if git tag | grep -q "^${TAG}$"; then
  echo "Error: tag ${TAG} already exists."
  exit 1
fi

# ── Update manifest.json ──────────────────────────────────────────────────────
CURRENT_VERSION=$(python3 -c "import json; print(json.load(open('${MANIFEST}'))['version'])")
echo "Bumping ${CURRENT_VERSION} → ${NEW_VERSION} in ${MANIFEST}"

python3 - <<EOF
import json, pathlib
p = pathlib.Path("${MANIFEST}")
data = json.loads(p.read_text())
data["version"] = "${NEW_VERSION}"
p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
EOF

# ── Commit ────────────────────────────────────────────────────────────────────
git add "${MANIFEST}"
git commit -m "chore: bump version to ${NEW_VERSION}"

# ── Tag ───────────────────────────────────────────────────────────────────────
git tag -a "${TAG}" -m "Release ${TAG}"
echo "Created tag ${TAG}"

# ── Push ─────────────────────────────────────────────────────────────────────
echo "Pushing commit and tag to origin…"
git push origin HEAD
git push origin "${TAG}"

echo ""
echo "Release ${TAG} pushed. GitHub Actions will create the release automatically."
