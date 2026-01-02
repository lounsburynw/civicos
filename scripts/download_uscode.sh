#!/bin/bash
# Download all U.S. Code titles in parallel from uscode.house.gov
# Release point: Public Law 119-59 (current as of Jan 2026)

set -e

OUTPUT_DIR="${1:-data/uscode}"
RELEASE="119-59"
BASE_URL="https://uscode.house.gov/download/releasepoints/us/pl/119/59"
MAX_PARALLEL=10

mkdir -p "$OUTPUT_DIR"

# All title numbers (including appendices like 5a)
TITLES=(
    01 02 03 04 05 05a 06 07 08 09
    10 11 11a 12 13 14 15 16 17 18 18a
    19 20 21 22 23 24 25 26 27 28 28a
    29 30 31 32 33 34 35 36 37 38
    39 40 41 42 43 44 45 46 47 48
    49 50 51 52 54
)

echo "=== U.S. Code Bulk Download ==="
echo "Release Point: PL $RELEASE"
echo "Output: $OUTPUT_DIR"
echo "Titles: ${#TITLES[@]}"
echo "Max parallel: $MAX_PARALLEL"
echo ""

# Track progress
TOTAL=${#TITLES[@]}
DONE=0
FAILED=()

download_title() {
    local title=$1
    local url="${BASE_URL}/xml_usc${title}@${RELEASE}.zip"
    local output="${OUTPUT_DIR}/xml_usc${title}.zip"

    if [[ -f "$output" ]]; then
        echo "[SKIP] Title $title (already exists)"
        return 0
    fi

    echo "[DOWN] Title $title..."
    if curl -sS --connect-timeout 30 --max-time 600 "$url" -o "$output.tmp" 2>/dev/null; then
        mv "$output.tmp" "$output"
        echo "[DONE] Title $title ($(du -h "$output" | cut -f1))"
        return 0
    else
        rm -f "$output.tmp"
        echo "[FAIL] Title $title"
        return 1
    fi
}

export -f download_title
export BASE_URL RELEASE OUTPUT_DIR

# Run parallel downloads
echo "Starting downloads..."
start_time=$(date +%s)

# Use xargs for parallel execution
printf '%s\n' "${TITLES[@]}" | xargs -P "$MAX_PARALLEL" -I {} bash -c 'download_title "$@"' _ {}

end_time=$(date +%s)
elapsed=$((end_time - start_time))

echo ""
echo "=== Download Complete ==="
echo "Time: ${elapsed}s"
echo "Files:"
ls -lh "$OUTPUT_DIR"/*.zip 2>/dev/null | wc -l | xargs echo "  Count:"
du -sh "$OUTPUT_DIR" | cut -f1 | xargs echo "  Total size:"

# Verify all titles downloaded
echo ""
echo "Verification:"
for title in "${TITLES[@]}"; do
    if [[ ! -f "${OUTPUT_DIR}/xml_usc${title}.zip" ]]; then
        echo "  MISSING: Title $title"
    fi
done
echo "Done."
