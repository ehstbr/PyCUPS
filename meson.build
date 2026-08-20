project(
  'print-archive',
  version: '0.1.11',
  meson_version: '>= 1.0.0',
)

i18n = import('i18n')
python = import('python').find_installation('python3')

python.install_sources(
  files(
    'src/print_archive/__init__.py',
    'src/print_archive/__main__.py',
    'src/print_archive/application.py',
    'src/print_archive/models.py',
  ),
  subdir: 'print_archive',
  pure: true,
)
python.install_sources(
  files(
    'src/print_archive/core/__init__.py',
    'src/print_archive/core/cups_service.py',
    'src/print_archive/core/documents.py',
    'src/print_archive/core/http.py',
    'src/print_archive/core/onboarding.py',
    'src/print_archive/core/page_ranges.py',
    'src/print_archive/core/preview.py',
    'src/print_archive/core/preview_view.py',
    'src/print_archive/core/print_preview.py',
    'src/print_archive/core/printer_capabilities.py',
    'src/print_archive/core/printer_selection.py',
    'src/print_archive/core/temp_store.py',
    'src/print_archive/core/updates.py',
    'src/print_archive/core/window_presentation.py',
  ),
  subdir: 'print_archive/core',
  pure: true,
)
python.install_sources(
  files(
    'src/print_archive/ui/__init__.py',
    'src/print_archive/ui/about.py',
    'src/print_archive/ui/about_content.py',
    'src/print_archive/ui/authentication.py',
    'src/print_archive/ui/cups_restart.py',
    'src/print_archive/ui/dialogs.py',
    'src/print_archive/ui/main_window.py',
    'src/print_archive/ui/onboarding.py',
    'src/print_archive/ui/printer_filter.py',
    'src/print_archive/ui/reprint_dialog.py',
    'src/print_archive/ui/settings.py',
    'src/print_archive/ui/update_window.py',
    'src/print_archive/ui/widgets.py',
  ),
  subdir: 'print_archive/ui',
  pure: true,
)
python.install_sources(
  files(
    'src/print_archive/util/__init__.py',
    'src/print_archive/util/async_runner.py',
    'src/print_archive/util/i18n.py',
  ),
  subdir: 'print_archive/util',
  pure: true,
)

launcher_configuration = configuration_data()
launcher_configuration.set('PYTHON', python.full_path())
configure_file(
  input: 'data/print-archive.in',
  output: 'print-archive',
  configuration: launcher_configuration,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: ['rwxr-xr-x'],
)

install_data(
  'data/com.eduhcommerce.PrintArchive.desktop',
  install_dir: join_paths(get_option('datadir'), 'applications'),
)
install_data(
  'data/com.eduhcommerce.PrintArchive.metainfo.xml',
  install_dir: join_paths(get_option('datadir'), 'metainfo'),
)
install_data(
  'data/icons/com.eduhcommerce.PrintArchive.svg',
  install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'scalable', 'apps'),
)
install_data(
  'data/icons/com.eduhcommerce.PrintArchive-symbolic.svg',
  install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'symbolic', 'apps'),
)
install_data(
  'packaging/apply-settings',
  install_dir: join_paths(get_option('prefix'), 'lib', 'print-archive'),
  install_mode: ['rwxr-xr-x'],
)
install_data(
  'data/com.eduhcommerce.PrintArchive.policy',
  install_dir: join_paths(get_option('datadir'), 'polkit-1', 'actions'),
)
install_data(
  'CHANGELOG.md',
  'LICENSE',
  'THIRD-PARTY.md',
  'version.json',
  install_dir: join_paths(get_option('datadir'), 'doc', 'print-archive'),
)

subdir('po')
