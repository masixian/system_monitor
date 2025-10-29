import subprocess
import logging
import uuid
import os
import re
from datetime import datetime

logging.basicConfig(filename='/var/log/system_monitor/systemmonitor.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class SoftwareInfo:
    def __init__(self, name, version, install_date=None, serial_number=None, uuid_str=None, manufacturer=None):
        self.software_name = name
        self.software_version = version
        self.install_date = install_date
        self.serial_number = serial_number
        self.uuid = uuid_str or str(uuid.uuid4())
        self.manufacturer = manufacturer or "Unknown"

    def to_dict(self):
        return {
            "SoftwareName": self.software_name,
            "SoftwareVersion": self.software_version,
            "InstallDate": self.install_date,
            "SerialNumber": self.serial_number,
            "UUID": self.uuid,
            "Manufacturer": self.manufacturer
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
    'grep', 'init', 'less', 'sed', 'language-pack-gnome-zh-hans', 'selinux-policy-targeted',
    'foomatic-db-compressed-ppds', 'foomatic-db-engine', 'hostname', 'init-system-helpers',
    'kcm', 'ksc-defender', 'ksc-set', 'ky-miracast-source', 'kysec-auth', 'kysec-daemon',
    'kysec-module-authorize-upgrade', 'kysec-sync-daemon', 'kyseclog-daemon',
    'linux-generic-hwe-v10pro', 'linux-hwe-5.10-headers-5.10.0-8', 'linux-modules-5.10.0-8-generic',
    'lsscsi', 'lzma', 'netbase', 'openprinting-ppds', 'optilauncher', 'parchives',
    'peony', 'peony-device-rename', 'peony-extensions', 'peony-open-terminal', 'peony-print-pictures',
    'peony-share', 'preinstalled-apps', 'python-is-python2', 'python3-pexpect',
    'qml-module-org-ukui-qqc2desktopstyle', 'qml-module-org-ukui-stylehelper',
    'qt5-ukui-platformtheme', 'screen-rotation-daemon', 'security-switch', 'sm-authorize',
    'systemd-enhance-conf', 'telnet', 'time', 'time-shutdown', 'ucf',
    'ukui-biometric-manager', 'ukui-bluetooth', 'ukui-clock', 'ukui-control-center',
    'ukui-desktop-environment', 'ukui-globaltheme-common', 'ukui-globaltheme-heyin',
    'ukui-globaltheme-light-seeking', 'ukui-greeter', 'ukui-kwin', 'ukui-media',
    'ukui-menu', 'ukui-notebook', 'ukui-notification-daemon', 'ukui-panel', 'ukui-polkit',
    'ukui-power-manager', 'ukui-screensaver', 'ukui-search', 'ukui-session-manager',
    'ukui-settings-daemon', 'ukui-sidebar', 'ukui-system-monitor', 'ukui-touch-settings-plugin',
    'ukui-window-switch', 'usb-modeswitch', 'xorgxrdp', 'xserver-xorg-video-nouveau',
    'xserver-xorg-video-qxl', 'xserver-xorg-video-vesa', 'youker-assistant', 'zenity', 'zip'
    # 注意：移除 'wps-office'，确保 WPS 被保留
}

EXCLUDED_PATTERNS = r'lib|kylin|麒麟|ukui|ubuntu|debian|font|printer|text|utils|tool|cups|language|policy|core|xserver|qml-module|qt5-ukui|linux-|systemd-'

def get_installed_software():
    try:
        manual_packages = set()
        try:
            result = subprocess.run(['apt-mark', 'showmanual'], capture_output=True, text=True)
            manual_packages = set(line.strip() for line in result.stdout.splitlines() if line.strip())
        except Exception as e:
            logging.error(f"Failed to get manual packages: {e}")

        packages = []
        result = subprocess.run(['dpkg', '-l'], capture_output=True, text=True)
        for line in result.stdout.splitlines()[5:]:
            parts = line.split()
            if len(parts) >= 3:
                name = parts[1]
                version = parts[2]
                if (name not in manual_packages or
                    name in EXCLUDED_SOFTWARE or
                    re.search(EXCLUDED_PATTERNS, name.lower(), re.IGNORECASE) or
                    re.search(EXCLUDED_PATTERNS, version.lower(), re.IGNORECASE)):
                    continue
                # 优化路径检查：针对 WPS 等大型软件，检查 /opt/kingsoft/wps-office 等特定路径
                executable_found = False
                if 'wps' in name.lower():
                    if os.path.exists('/opt/kingsoft/wps-office'):
                        executable_found = True
                else:
                    for path in ['/opt', '/usr/local/bin']:
                        if os.path.exists(os.path.join(path, name)) or any(name in f for f in os.listdir(path) if os.path.isdir(os.path.join(path, f))):
                            executable_found = True
                            break
                if not executable_found:
                    continue
                install_date = None
                try:
                    log_result = subprocess.run(['grep', f'install {name}:', '/var/log/dpkg.log'], capture_output=True, text=True)
                    for log_line in log_result.stdout.splitlines():
                        if 'install' in log_line:
                            date_str = log_line.split()[0]
                            install_date = datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%m-%d')
                            break
                    if not install_date:
                        status_result = subprocess.run(['grep', f'^{name} ', '/var/lib/dpkg/status'], capture_output=True, text=True)
                        for status_line in status_result.stdout.splitlines():
                            if status_line.startswith('Installed-Time'):
                                timestamp = int(status_line.split()[1])
                                install_date = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
                                break
                    if not install_date:
                        for path in ['/opt', '/usr/local/bin']:
                            if os.path.exists(os.path.join(path, name)):
                                install_date = datetime.fromtimestamp(os.path.getctime(os.path.join(path, name))).strftime('%Y-%m-%d')
                                break
                except:
                    logging.error(f"Failed to get install date for {name}")
                packages.append(SoftwareInfo(name, version, install_date, None, str(uuid.uuid4()), "Unknown"))
        logging.info(f"Software info collected successfully: {len(packages)} packages")
        return packages
    except Exception as e:
        logging.error(f"Failed to collect software info: {e}")
        return []