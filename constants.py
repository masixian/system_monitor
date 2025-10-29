import re

EXCLUDED_PROCESSES = {
    "init", "systemd", "bash", "sshd", "cron", "udevd", "dbus-daemon",
    "kworker", "ksoftirqd", "systemd-journald", "systemd-udevd", "cupsd"
}

EXCLUDED_SOFTWARE = {
    'accountsservice', 'acl', 'bash', 'coreutils', 'dpkg', 'systemd', 'alsa-topology-conf',
    'android-libaapt', 'android-libandroidfw', 'android-libboringssl', 'android-libunwind',
    'apng2gif', 'apngasm', 'attr', 'base-passwd', 'bc', 'biometric-auth',
    'biometric-driver-aratek-trustfinger', 'biometric-driver-aratek-trustfinger-common',
    'biometric-driver-community-multidevice', 'biometric-driver-mh-ukey',
    'biometric-driver-mh-ukey-common', 'biometric-driver-r301', 'biometric-driver-seetaface-detect',
    'biometric-driver-seetaface-detect-common', 'biometric-driver-wechat',
    'biometric-driver-wechat-common', 'biometric-utils', 'box-manager', 'box-utils',
    'bzip2', 'cdrdao', 'cdrskin', 'certaide-kylin', 'certmonger', 'chpolicy',
    'colord', 'colord-data', 'command-not-found', 'crda', 'curlftpfs', 'dc', 'dconf-cli',
    'dconf-gsettings-backend', 'dconf-service', 'debconf', 'debconf-i18n', 'dictionaries-common',
    'diffutils', 'dosfstools', 'edid-decode', 'eject', 'emacsen-common', 'ethtool',
    'exfat-fuse', 'exfat-utils', 'fakeroot', 'ffmpegthumbnailer', 'finalrd',
    'fonts-dejavu-core', 'fonts-droid-fallback', 'fonts-freefont-ttf', 'fonts-mathjax', 'fonts-noto',
    'cups', 'cups-browsed', 'cups-daemon', 'printer-driver'
}

EXCLUDED_PATTERNS = r'lib|kylin|麒麟|ubuntu|debian|font|printer|text|utils|tool|cups|editor'