#!/usr/bin/env bash
# publish_badge.sh FILE...: commit badge JSON files to the `badges` branch
# (created as an orphan branch on first use). Used by CI with a token that
# has contents: write; the branch holds nothing but badge JSON.
set -euo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"

work="$(mktemp -d)"
files=()
for f in "$@"; do files+=("$(cd "$(dirname "$f")" && pwd)/$(basename "$f")"); done

cd "$work"
git init -q
git remote add origin "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
if git fetch -q --depth 1 origin badges 2>/dev/null; then
  git checkout -q -B badges FETCH_HEAD
else
  git checkout -q --orphan badges
fi

cp "${files[@]}" .
git add -- "${files[@]##*/}"
if git diff --cached --quiet; then
  echo "badges unchanged"
  exit 0
fi
git -c user.name="github-actions[bot]" \
    -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
    commit -q -m "chore: update ${files[*]##*/}"
git push -q origin badges
echo "published ${files[*]##*/}"
