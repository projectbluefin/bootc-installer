project('org.bootcinstaller.Installer',
          version: '3.0.0',
    meson_version: '>= 0.59.0',
  default_options: [ 'warning_level=2',
                     'werror=false',
                   ],
)

python = import('python')
py_inst = python.find_installation('python3')

i18n = import('i18n')

gnome = import('gnome')

subdir('data')
if get_option('build-fisherman')
  subdir('fisherman')
endif
subdir('bootc_installer')
subdir('po')

gnome.post_install(
  glib_compile_schemas: true,
  gtk_update_icon_cache: true,
  update_desktop_database: true,
)
