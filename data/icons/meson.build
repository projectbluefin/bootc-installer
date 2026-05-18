variant = get_option('variant')

if variant == 'xfce'
  application_id = 'org.xfceinstaller.Installer'
elif variant == 'kde'
  application_id = 'org.kdeinstaller.Installer'
else
  application_id = 'org.bootcinstaller.Installer'
endif


scalable_dir = join_paths('hicolor', 'scalable', 'apps')
symbolic_dir = join_paths('hicolor', 'symbolic')
actions_dir = join_paths(symbolic_dir, 'actions')


install_data(
  join_paths(scalable_dir, 'org.bootcinstaller.Installer.svg'),
  install_dir: join_paths(get_option('datadir'), 'icons', scalable_dir),
  rename: application_id + '.svg'
)

install_data(
  join_paths(scalable_dir, ('@0@.svg').format('org.vanillaos.Installer-flower')),
  install_dir: join_paths(get_option('datadir'), 'icons', scalable_dir)
)

install_data(
  join_paths(symbolic_dir, 'apps', 'org.bootcinstaller.Installer-symbolic.svg'),
  install_dir: join_paths(get_option('datadir'), 'icons', symbolic_dir, 'apps'),
  rename: application_id + '-symbolic.svg'
)


install_data(
    join_paths(actions_dir, 'background-app-ghost-symbolic.svg'),
    install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'scalable', 'actions')
)
install_data(
    join_paths(actions_dir, 'vanilla-installer-harddisk-symbolic.svg'),
    install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'scalable', 'actions')
)
install_data(
    join_paths(actions_dir, 'vanilla-installer-display-with-window-symbolic.svg'),
    install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'scalable', 'actions')
)
install_data(
    join_paths(actions_dir, 'vanilla-logo-text-symbolic.svg'),
    install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'scalable', 'actions')
)
