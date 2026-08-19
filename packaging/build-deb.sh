#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="${1:-$project_root/dist}"
package_name="print-archive"
source_date_epoch="${SOURCE_DATE_EPOCH:-1787157949}"

for command_name in dpkg-deb install find sort xargs md5sum gzip sed grep du awk mktemp rm touch chmod msgfmt; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "Required build command not found: $command_name" >&2
        exit 2
    fi
done

version="$(sed -n 's/^VERSION = "\([^"]*\)"/\1/p' "$project_root/src/print_archive/__init__.py")"
if [[ -z "$version" ]]; then
    echo "Could not determine the application version." >&2
    exit 2
fi
for version_file in "$project_root/meson.build" "$project_root/pyproject.toml" "$project_root/data/com.eduhcommerce.PrintArchive.metainfo.xml"; do
    if ! grep -Fq "$version" "$version_file"; then
        echo "Version $version is not present in ${version_file#$project_root/}." >&2
        exit 2
    fi
done

"$project_root/tools/compile-translations.sh"

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/print-archive-deb.XXXXXX")"
cleanup() {
    case "$work_dir" in
        /tmp/print-archive-deb.*|"${TMPDIR:-/tmp}"/print-archive-deb.*) rm -rf -- "$work_dir" ;;
    esac
}
trap cleanup EXIT

package_root="$work_dir/${package_name}_${version}_all"
python_dir="$package_root/usr/lib/python3/dist-packages"
doc_dir="$package_root/usr/share/doc/$package_name"

install -d -m 0755 \
    "$package_root/DEBIAN" \
    "$package_root/usr/bin" \
    "$python_dir" \
    "$package_root/usr/lib/print-archive" \
    "$package_root/usr/share/applications" \
    "$package_root/usr/share/metainfo" \
    "$package_root/usr/share/icons/hicolor/scalable/apps" \
    "$package_root/usr/share/icons/hicolor/symbolic/apps" \
    "$package_root/usr/share/polkit-1/actions" \
    "$doc_dir"

while IFS= read -r -d '' source_file; do
    relative_path="${source_file#$project_root/src/}"
    install -D -m 0644 "$source_file" "$python_dir/$relative_path"
done < <(find "$project_root/src/print_archive" -type f -name '*.py' -print0 | sort -z)

install -m 0755 "$project_root/packaging/debian/print-archive" "$package_root/usr/bin/print-archive"
install -m 0755 "$project_root/packaging/apply-settings" "$package_root/usr/lib/print-archive/apply-settings"
install -m 0644 "$project_root/data/com.eduhcommerce.PrintArchive.desktop" "$package_root/usr/share/applications/"
install -m 0644 "$project_root/data/com.eduhcommerce.PrintArchive.metainfo.xml" "$package_root/usr/share/metainfo/"
install -m 0644 "$project_root/data/icons/com.eduhcommerce.PrintArchive.svg" "$package_root/usr/share/icons/hicolor/scalable/apps/"
install -m 0644 "$project_root/data/icons/com.eduhcommerce.PrintArchive-symbolic.svg" "$package_root/usr/share/icons/hicolor/symbolic/apps/"
install -m 0644 "$project_root/data/com.eduhcommerce.PrintArchive.policy" "$package_root/usr/share/polkit-1/actions/"
install -D -m 0644 \
    "$project_root/locale/pt_BR/LC_MESSAGES/print-archive.mo" \
    "$package_root/usr/share/locale/pt_BR/LC_MESSAGES/print-archive.mo"

install -m 0644 \
    "$project_root/README.md" \
    "$project_root/README.pt-BR.md" \
    "$project_root/LICENSE" \
    "$project_root/THIRD-PARTY.md" \
    "$project_root/version.json" \
    "$doc_dir/"
install -m 0644 "$project_root/packaging/debian/copyright" "$doc_dir/copyright"
gzip -9nc "$project_root/CHANGELOG.md" > "$doc_dir/changelog.gz"
gzip -9nc "$project_root/packaging/debian/changelog" > "$doc_dir/changelog.Debian.gz"

install -m 0755 "$project_root/packaging/debian/postinst" "$package_root/DEBIAN/postinst"
install -m 0755 "$project_root/packaging/debian/postrm" "$package_root/DEBIAN/postrm"

installed_size="$(du -sk "$package_root/usr" | awk '{print $1}')"
sed \
    -e "s/@VERSION@/$version/g" \
    -e "s/@INSTALLED_SIZE@/$installed_size/g" \
    "$project_root/packaging/debian/binary-control.in" > "$package_root/DEBIAN/control"
chmod 0644 "$package_root/DEBIAN/control"

(
    cd "$package_root"
    find usr -type f -print0 | sort -z | xargs -0 md5sum
) > "$package_root/DEBIAN/md5sums"
chmod 0644 "$package_root/DEBIAN/md5sums"

find "$package_root" -exec touch -h -d "@$source_date_epoch" {} +
install -d -m 0755 "$output_dir"
output_file="$output_dir/${package_name}_${version}_all.deb"
SOURCE_DATE_EPOCH="$source_date_epoch" dpkg-deb \
    --root-owner-group \
    --uniform-compression \
    -Zxz -z9 \
    --build "$package_root" "$output_file"

echo "$output_file"
sha256sum "$output_file"
