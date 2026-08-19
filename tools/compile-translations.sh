#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for language in pt_BR; do
    source_file="$project_root/po/$language.po"
    target_dir="$project_root/locale/$language/LC_MESSAGES"
    target_file="$target_dir/print-archive.mo"
    mkdir -p "$target_dir"
    msgfmt --check --check-format --output-file="$target_file" "$source_file"
done

