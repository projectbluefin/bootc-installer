# Tuna Installer Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.5.0] - 2026-05-08

### 🚀 Major Features

#### ZFS Filesystem Support
- **ZFS Root Installation**: Full support for ZFS as root filesystem option
- **ZFS Dependencies**: Auto-detect and provision `zfsutils-linux` and `zpool` tools
- **ZFS UI Integration**: Added "ZFS" option to filesystem dropdown alongside XFS and Btrfs

#### Ubuntu 26.04 Support
- **New Linux Distribution**: Added Ubuntu 26.04 with ZFS filesystem support
- **Extended OS Matrix**: Expanded bootcrew testing matrix with Ubuntu 26.04 variant

### 🔄 Updated Dependencies

#### Fisherman Submodule Bump
- **New Version**: ae831106 → 582639d
- **Changes Include**:
  - Composefs overlay storage support
  - ext4 root filesystem with verity
  - Improved systemd-boot EFI handling
  - Enhanced storage driver detection
  - SSH/boot verification improvements
  - Release automation workflows
  - Storage driver and LUKS test coverage

#### .gitmodules Update
- Changed fisherman submodule tracking from `branch = dev` to `branch = prod`
- Ensures installer production builds use stable fisherman prod releases

#### Build Tools
- Added `btrfs-progs.tar.xz` for offline btrfs support
- Added `popt.tar.xz` dependency archive

### 🐛 Bug Fixes & Improvements
- Enhanced disk page to show filesystem tool availability
- Better handling of missing mkfs tools before installation
- Improved user creation and recovery dialog workflows

---

## [2.4.0] - 2026-04-XX

### Previous Features
- GTK4/Libadwaita modern UI
- Multi-OS bootc image installation
- Custom partitioning with XFS/Btrfs
- LUKS encryption
- Composefs with systemd-boot
- Offline installation support
- Recovery mode
- User account creation
