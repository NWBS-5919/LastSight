#!/bin/bash
# aihubshell의 병합 로직에 한글 파일명 버그가 있어(printf %q 이스케이프가 find -name과 안 맞음),
# 다운로드는 AI Hub API를 직접 호출하고 병합은 bash glob으로 직접 처리한다.
set -euo pipefail

DATASETKEY="$1"
FILEKEY="$2"
APIKEY="$3"
DEST_DIR="$4"

mkdir -p "$DEST_DIR"
cd "$DEST_DIR"

curl -sL -C - -o download.tar -H "apikey:$APIKEY" \
  "https://api.aihub.or.kr/down/0.6/${DATASETKEY}.do?fileSn=${FILEKEY}"

tar -xf download.tar
rm -f download.tar

# 모든 하위 폴더에서 .part* 파일을 찾아 bash glob으로 병합 (UTF-8 파일명 안전)
find . -type d | while IFS= read -r dir; do
  shopt -s nullglob
  for part in "$dir"/*.part0; do
    prefix="${part%.part0}"
    cat "$prefix".part* > "$prefix"
    rm -f "$prefix".part*
  done
  shopt -u nullglob
done
