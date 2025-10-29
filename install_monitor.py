import time
import json
import logging
import subprocess
import os
from inotify.adapters import Inotify
from inotify.constants import IN_CREATE, IN_DELETE
import psutil
from rabbitmq_service import RabbitMQService
from process_monitor import EXCLUDED_PROCESSES, EXCLUDED_PROCESS_PATTERNS
from software_info import EXCLUDED_SOFTWARE, EXCLUDED_PATTERNS
import re

logging.basicConfig(filename='/var/log/system_monitor/systemmonitor.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class MonitorMessage:
    def __init__(self, device_id):
        self.device_id = device_id
        self.type = ""
        self.timestamp = ""
        self.data = {}

    def to_dict(self):
        return {
            "DeviceId": self.device_id,
            "Type": self.type,
            "Timestamp": self.timestamp,
            "Data": self.data
        }

class InstallMonitor:
    def __init__(self, rabbitmq_service, device_id):
        self.rabbitmq_service = rabbitmq_service
        self.device_id = device_id
        self.last_processes = set()
        self.last_packages = set()
        self.inotify = None

    def start_monitoring(self):
        watch_dirs = ['/var/lib/dpkg/info', '/usr', '/opt']
        try:
            self.inotify = Inotify()
            for watch_dir in watch_dirs:
                if not os.path.exists(watch_dir):
                    logging.error(f"Directory {watch_dir} does not exist, attempting to create")
                    os.makedirs(watch_dir, exist_ok=True)
                self.inotify.add_watch(watch_dir, mask=IN_CREATE | IN_DELETE)
                logging.info(f"Monitoring {watch_dir} for install/uninstall events")
            self.update_last_processes()
            self.update_last_packages()
            
            for event in self.inotify.event_gen(yield_nones=False):
                (_, type_names, path, filename) = event
                action = 'SoftwareInstall' if 'IN_CREATE' in type_names else 'SoftwareUninstall'
                message = MonitorMessage(self.device_id)
                message.type = action
                message.timestamp = time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+08:00'
                message.data = {"softwareName": filename}
                self.rabbitmq_service.send_message(message.to_dict())
                logging.info(f"{action}: {filename}")

                current_processes = {f"{proc.info['pid']}:{proc.info['name']}" for proc in psutil.process_iter(['pid', 'name'])}
                new_processes = current_processes - self.last_processes
                for proc_str in new_processes:
                    try:
                        pid, name = proc_str.split(':', 1)
                        if (name in EXCLUDED_PROCESSES or
                            re.search(EXCLUDED_PROCESS_PATTERNS, name.lower(), re.IGNORECASE)):
                            continue
                        proc = psutil.Process(int(pid))
                        path = proc.exe() or "N/A"
                        if path == "N/A" or not (path.startswith('/opt') or path.startswith('/usr/local/bin')):
                            continue
                        message = MonitorMessage(self.device_id)
                        message.type = "ProcessStart"
                        message.timestamp = time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+08:00'
                        message.data = {
                            "processName": name,
                            "filePath": path
                        }
                        self.rabbitmq_service.send_message(message.to_dict())
                        logging.info(f"New process: {message.data}")
                    except:
                        pass
                self.last_processes = current_processes

                manual_packages = set()
                try:
                    result = subprocess.run(['apt-mark', 'showmanual'], capture_output=True, text=True)
                    manual_packages = set(line.strip() for line in result.stdout.splitlines() if line.strip())
                except:
                    logging.error("Failed to get manual packages")
                current_packages = set(subprocess.run(['dpkg', '-l'], capture_output=True, text=True).stdout.splitlines()[5:])
                new_packages = current_packages - self.last_packages
                removed_packages = self.last_packages - current_packages
                for pkg in new_packages:
                    parts = pkg.split()
                    if (len(parts) >= 3 and 
                        parts[1] in manual_packages and
                        parts[1] not in EXCLUDED_SOFTWARE and
                        not re.search(EXCLUDED_PATTERNS, parts[1].lower(), re.IGNORECASE) and
                        not re.search(EXCLUDED_PATTERNS, parts[2].lower(), re.IGNORECASE)):
                        executable_found = False
                        if 'wps' in parts[1].lower():
                            if os.path.exists('/opt/kingsoft/wps-office'):
                                executable_found = True
                        else:
                            for path in ['/opt', '/usr/local/bin']:
                                if os.path.exists(os.path.join(path, parts[1])) or any(parts[1] in f for f in os.listdir(path) if os.path.isdir(os.path.join(path, f))):
                                    executable_found = True
                                    break
                        if not executable_found:
                            continue
                        message = MonitorMessage(self.device_id)
                        message.type = "SoftwareInstall"
                        message.timestamp = time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+08:00'
                        message.data = {"softwareName": parts[1], "version": parts[2]}
                        self.rabbitmq_service.send_message(message.to_dict())
                        logging.info(f"Software installed: {parts[1]}")
                for pkg in removed_packages:
                    parts = pkg.split()
                    if len(parts) >= 3:
                        message = MonitorMessage(self.device_id)
                        message.type = "SoftwareUninstall"
                        message.timestamp = time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+08:00'
                        message.data = {"softwareName": parts[1]}
                        self.rabbitmq_service.send_message(message.to_dict())
                        logging.info(f"Software uninstalled: {parts[1]}")
                self.last_packages = current_packages

                time.sleep(3)

        except Exception as e:
            logging.error(f"Monitoring failed: {e}")
        finally:
            if self.inotify:
                try:
                    for watch_dir in watch_dirs:
                        self.inotify.remove_watch(watch_dir)
                        logging.info(f"Stopped monitoring {watch_dir}")
                except Exception as e:
                    logging.error(f"Failed to remove watch: {e}")

    def update_last_processes(self):
        self.last_processes = {f"{proc.info['pid']}:{proc.info['name']}" for proc in psutil.process_iter(['pid', 'name']) 
                              if proc.info['name'] not in EXCLUDED_PROCESSES and 
                              not re.search(EXCLUDED_PROCESS_PATTERNS, proc.info['name'].lower(), re.IGNORECASE)}

    def update_last_packages(self):
        self.last_packages = set(subprocess.run(['dpkg', '-l'], capture_output=True, text=True).stdout.splitlines()[5:])