pkgdatadir = join_paths(get_option('prefix'), get_option('datadir'), meson.project_name())
viewsdir = join_paths(pkgdatadir, 'bootc_installer/views')

sources = [
  '__init__.py',
  'confirm.py',
  'confirm_data.py',
  'done.py',
  'progress.py',
  'recovery_key.py',
  'tour.py',
]

install_data(sources, install_dir: viewsdir)
