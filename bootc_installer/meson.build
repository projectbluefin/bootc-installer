pkgdatadir = join_paths(get_option('prefix'), get_option('datadir'), meson.project_name())
moduledir = join_paths(pkgdatadir, 'bootc_installer')
gnome = import('gnome')

blueprint_compiler = find_program('blueprint-compiler', required: false)

if blueprint_compiler.found()
  blueprints = custom_target(
    'blueprints',
    input: files(
      'gtk/confirm.blp',
      'gtk/default-conn-check.blp',
      'gtk/default-disk.blp',
      'gtk/default-encryption.blp',
      'gtk/default-hardware.blp',
      'gtk/default-image.blp',
      'gtk/default-network.blp',
      'gtk/default-nvidia.blp',
      'gtk/default-slurp.blp',
      'gtk/default-theme.blp',
      'gtk/default-users.blp',
      'gtk/default-vm.blp',
      'gtk/default-welcome.blp',
      'gtk/dialog.blp',
      'gtk/dialog-disk.blp',
      'gtk/dialog-disk-confirm.blp',
      'gtk/dialog-credits.blp',
      'gtk/dialog-output.blp',
      'gtk/dialog-poweroff.blp',
      'gtk/dialog-recovery.blp',
      'gtk/done.blp',
      'gtk/layout-preferences.blp',
      'gtk/layout-yes-no.blp',
      'gtk/progress.blp',
      'gtk/recovery-key.blp',
      'gtk/tour.blp',
      'gtk/widget-choice.blp',
      'gtk/widget-page-header.blp',
      'gtk/widget-choice-expander.blp',
      'gtk/widget-disk.blp',
      'gtk/widget-partition.blp',
      'gtk/widget-partition-row.blp',
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
  resources_deps = blueprints
else
  resources_deps = []
  warning('blueprint-compiler not found, skipping UI compilation')
endif

gnome.compile_resources('bootc-installer',
  'bootc-installer.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
  dependencies: resources_deps,
)

python = import('python')

conf = configuration_data()
conf.set('PYTHON', python.find_installation('python3').full_path())
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
subdir('data')
subdir('layouts')
subdir('core')
subdir('utils')
subdir('views')
subdir('widgets')
subdir('windows')

# Bake the Meson project version into _version.py at build time.
configure_file(
  input: '_version.py.in',
  output: '_version.py',
  configuration: conf,
  install: true,
  install_dir: moduledir,
)

install_data(['__init__.py', 'main.py'], install_dir: moduledir)
