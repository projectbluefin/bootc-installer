pkgdatadir = join_paths(get_option('prefix'), get_option('datadir'), meson.project_name())
defaultsdir = join_paths(pkgdatadir, 'bootc_installer/defaults')

sources = [
  '__init__.py',
  'welcome.py',
  'disk.py',
  'slurp.py',
  'encryption.py',
  'image.py',
  'nvidia.py',
  'vm.py',
  'conn_check.py',
  'network.py',
  'theme.py',
  'user.py',
  'qr_companion.py',
]

install_data(sources, install_dir: defaultsdir)
