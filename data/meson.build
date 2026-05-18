install_data(
    'installer.desktop',
    install_dir: join_paths(get_option('datadir'), 'xsessions')
)

install_data(
    'installer.desktop',
    install_dir: join_paths(get_option('datadir'), 'wayland-sessions')
)

install_data(
    'installer.desktop',
    install_dir: join_paths(get_option('datadir'), 'gnome-session', 'sessions')
)

install_data(
    'installer.json',
    install_dir: join_paths(get_option('datadir'), 'gnome-shell', 'modes')
)

install_data(
    'org.bootcinstaller.Installer.policy',
    install_dir: join_paths(get_option('datadir'), 'polkit-1', 'actions')
)

if variant == 'xfce'
  install_data('polkit/org.xfceinstaller.Installer.policy',
    install_dir: join_paths(get_option('datadir'), 'polkit-1', 'actions')
  )
endif

if variant == 'kde'
  install_data('polkit/org.kdeinstaller.Installer.policy',
    install_dir: join_paths(get_option('datadir'), 'polkit-1', 'actions')
  )
endif

desktop_file = i18n.merge_file(
  input: 'org.bootcinstaller.Installer.desktop.in',
  output: 'org.bootcinstaller.Installer.desktop',
  type: 'desktop',
  po_dir: '../po',
  install: true,
  install_dir: join_paths(get_option('datadir'), 'applications')
)

if variant == 'xfce'
  xfce_desktop_file = i18n.merge_file(
    input: 'org.xfceinstaller.Installer.desktop.in',
    output: 'org.xfceinstaller.Installer.desktop',
    type: 'desktop',
    po_dir: '../po',
    install: true,
    install_dir: join_paths(get_option('datadir'), 'applications')
  )
endif

if variant == 'kde'
  kde_desktop_file = i18n.merge_file(
    input: 'org.kdeinstaller.Installer.desktop.in',
    output: 'org.kdeinstaller.Installer.desktop',
    type: 'desktop',
    po_dir: '../po',
    install: true,
    install_dir: join_paths(get_option('datadir'), 'applications')
  )
endif

desktop_utils = find_program('desktop-file-validate', required: false)
if desktop_utils.found()
  test('Validate desktop file', desktop_utils,
    args: [desktop_file]
  )
endif

appstream_file = i18n.merge_file(
  input: 'org.bootcinstaller.Installer.appdata.xml.in',
  output: 'org.bootcinstaller.Installer.appdata.xml',
  po_dir: '../po',
  install: true,
  install_dir: join_paths(get_option('datadir'), 'appdata')
)

if variant == 'xfce'
  xfce_appstream_file = i18n.merge_file(
    input: 'org.xfceinstaller.Installer.appdata.xml.in',
    output: 'org.xfceinstaller.Installer.appdata.xml',
    po_dir: '../po',
    install: true,
    install_dir: join_paths(get_option('datadir'), 'appdata')
  )
endif

if variant == 'kde'
  kde_appstream_file = i18n.merge_file(
    input: 'org.kdeinstaller.Installer.appdata.xml.in',
    output: 'org.kdeinstaller.Installer.appdata.xml',
    po_dir: '../po',
    install: true,
    install_dir: join_paths(get_option('datadir'), 'appdata')
  )
endif

# AppStream validation disabled - icon validation fails in Flatpak CI environment
# appstream_util = find_program('appstream-util', required: false)
# if appstream_util.found()
#   test('Validate appstream file', appstream_util,
#     args: ['validate', appstream_file]
#   )
# endif

install_data('org.bootcinstaller.Installer.gschema.xml',
  install_dir: join_paths(get_option('datadir'), 'glib-2.0/schemas')
)

compile_schemas = find_program('glib-compile-schemas', required: false)
if compile_schemas.found()
  test('Validate schema file', compile_schemas,
    args: ['--strict', '--dry-run', meson.current_source_dir()]
  )
endif

install_data('../recipe.json',
  install_dir: join_paths(get_option('datadir'), 'bootc-installer')
)

install_data('../fisherman/data/images.json',
  install_dir: join_paths(get_option('datadir'), 'bootc-installer')
)

subdir('icons')
