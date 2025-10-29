import psutil
import logging
import re

logging.basicConfig(filename='/var/log/system_monitor/systemmonitor.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class ProcessInfo:
    def __init__(self):
        self.name = "N/A"
        self.path = "N/A"
        self.process_id = 0

    def to_dict(self):
        return {
            "Name": self.name,
            "Path": self.path,
            "ProcessId": self.process_id
        }

EXCLUDED_PROCESSES = {
    'init', 'systemd', 'bash', 'sshd', 'cron', 'udevd', 'dbus-daemon',
    'kworker', 'ksoftirqd', 'systemd-journald', 'systemd-udevd', 'cupsd',
    'idle_inject', 'irq', 'scsi', 'python3', 'ukui', 'kylin', 'sh', 'gnome', 'qax',
    'kthreadd', 'rcu_gp', 'rcu_par_gp', 'mm_percpu_wq', 'rcu_tasks_rude_',
    'rcu_tasks_trace', 'migration', 'cpuhp', 'kdevtmpfs', 'netns', 'kauditd',
    'khungtaskd', 'oom_reaper', 'writeback', 'kcompactd0', 'ksmd', 'khugepaged',
    'kintegrityd', 'kblockd', 'blkcg_punt_bio', 'tpm_dev_wq', 'ata_sff', 'md',
    'edac-poller', 'devfreq_wq', 'watchdogd', 'kysec_auth', 'kswapd0', 'ecryptfs-kthrea',
    'kthrotld', 'mpt_poll_0', 'mpt', 'cryptd', 'vmwgfx', 'ttm_swap', 'card0-crtc',
    'scsi_eh', 'scsi_tmf', 'jbd2', 'ext4-rsv-conver', 'kysec_notify_th',
    'audit_prune_tre', 'system_monitor'
}

EXCLUDED_PROCESS_PATTERNS = r'kylin|ukui|gnome|qax|irq|scsi|jbd2|ext4|rcu_|kworker'

def get_running_processes():
    process_list = []
    try:
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            name = proc.info['name']
            if (name in EXCLUDED_PROCESSES or
                re.search(EXCLUDED_PROCESS_PATTERNS, name.lower(), re.IGNORECASE)):
                continue
            try:
                path = proc.info['exe'] or "N/A"
                if path == "N/A" or not (path.startswith('/opt') or path.startswith('/usr/local/bin')):
                    continue
                process = ProcessInfo()
                process.name = name
                process.path = path
                process.process_id = proc.info['pid']
                process_list.append(process)
            except:
                pass
        logging.info(f"Running processes collected successfully: {len(process_list)} processes")
        return process_list
    except Exception as e:
        logging.error(f"Failed to collect processes: {e}")
        return []