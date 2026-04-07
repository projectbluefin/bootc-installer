pkgdatadir = join_paths(get_option('prefix'), get_option('datadir'), meson.project_name())
moduledir = join_paths(pkgdatadir, 'bootc_installer')
gnome = import('gnome')

blueprint_compiler = find_program('blueprint-compiler', version: '>= 0.12.0')

blueprints = custom_target(
  'blueprints',
  input: files(
    'gtk/confirm.blp',
    'gtk/default-conn-check.blp',
    'gtk/default-disk.blp',
    'gtk/default-encryption.blp',
    'gtk/default-image.blp',
    'gtk/default-keyboard.blp',
    'gtk/default-language.blp',
    'gtk/default-network.blp',
    'gtk/default-nvidia.blp',
    'gtk/default-theme.blp',
    'gtk/default-timezone.blp',
    'gtk/default-users.blp',
    'gtk/default-vm.blp',
    'gtk/default-welcome.blp',
    'gtk/dialog.blp',
    'gtk/dialog-disk.blp',
    'gtk/dialog-disk-confirm.blp',
    'gtk/dialog-output.blp',
    'gtk/dialog-poweroff.blp',
    'gtk/dialog-recovery.blp',
    'gtk/done.blp',
    'gtk/layout-preferences.blp',
    'gtk/layout-yes-no.blp',
    'gtk/progress.blp',
    'gtk/tour.blp',
    'gtk/widget-choice.blp',
    'gtk/widget-page-header.blp',
    'gtk/widget-choice-expander.blp',
    'gtk/widget-disk.blp',
    'gtk/widget-keyboard.blp',
    'gtk/widget-language.blp',
    'gtk/widget-partition.blp',
    'gtk/widget-partition-row.blp',
    'gtk/widget-timezone.blp',
    'gtk/window.blp',
    'gtk/window-cpu.blp',
    'gtk/window-ram.blp',
    'gtk/window-unsupported.blp',
    'gtk/wireless-row.blp',
  ),
  output: '.',
  command: [
    blueprint_compiler,
    'batch-compile',
    '@OUTPUT@',
    '@CURRENT_SOURCE_DIR@',
    '@INPUT@',
  ],
)

gnome.compile_resources('bootc-installer',
  'bootc-installer.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
  dependencies: blueprints,
)

python = import('python')

conf = configuration_data()
conf.set('PYTHON', python.find_installation('python3').path())
conf.set('VERSION', meson.project_version())
conf.set('localedir', join_paths(get_option('prefix'), get_option('localedir')))
conf.set('pkgdatadir', pkgdatadir)

configure_file(
  input: 'bootc-installer.in',
  output: 'bootc-installer',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x'
)

configure_file(
  input: 'bootc-installer-processor.in',
  output: 'bootc-installer-processor',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x'
)

subdir('defaults')
subdir('layouts')
subdir('core')
subdir('utils')
subdir('views')
subdir('widgets')
subdir('windows')

# Bake the git describe string (e.g. "v2.3.7-14-gabcdef0") into _version.py at
# build time. Falls back to the VERSION file content when git is unavailable
# (e.g. inside a Flatpak build sandbox that strips .git).
_version_from_file = run_command('cat', meson.source_root() / 'VERSION', check: false).stdout().strip()
_version_fallback = _version_from_file != '' ? _version_from_file : meson.project_version()

custom_target(
  '_version.py',
  output: '_version.py',
  command: [
    'python3', '-c',
    'import subprocess,sys; r=subprocess.run(["git","-C",sys.argv[1],"describe","--tags","--always","--dirty"],capture_output=True,text=True); v=r.stdout.strip() if r.returncode==0 and r.stdout.strip() else sys.argv[2]; open(sys.argv[3],"w").write(f"VERSION = {v!r}\\n")',
    meson.source_root(),
    _version_fallback,
    '@OUTPUT@',
  ],
  build_by_default: true,
  install: true,
  install_dir: moduledir,
)
