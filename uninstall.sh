#!/bin/bash

INSTALL_DIR="/opt/system_monitor"
SERVICE_NAME="system-monitor"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"
LOG_DIR="/var/log/system_monitor"
CACHE_DIR="$INSTALL_DIR/cache"
CONFIG_FILE="$INSTALL_DIR/config.json"

# 检查 root 权限
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root"
    exit 1
fi

# 获取设备 ID
DEVICE_ID=$(ip addr show | grep -B2 ether | grep -v lo | grep -v wlan | head -n1 | awk '{print $2}' | tr -d ':' | tr '[:upper:]' '[:lower:]')
if [ -z "$DEVICE_ID" ]; then
    echo "Error: Could not determine device ID"
    exit 1
fi

# 获取服务器密码
TEMP_PASS_FILE="/tmp/system_monitor_pass.txt"
if ! /opt/system_monitor/get_password "$TEMP_PASS_FILE"; then
    echo "Error: Failed to retrieve password from server"
    exit 1
fi
if [ ! -f "$TEMP_PASS_FILE" ]; then
    echo "Error: Password file not created"
    exit 1
fi
SERVER_PASSWORD=$(cat "$TEMP_PASS_FILE")
rm -f "$TEMP_PASS_FILE"

# 提示用户输入密码
echo "Enter password to uninstall System Monitor:"
read -s USER_PASSWORD
echo

# 验证密码
if [ "$USER_PASSWORD" != "$SERVER_PASSWORD" ]; then
    echo "Error: Incorrect password"
    exit 1
fi

# 停止服务
echo "Stopping System Monitor service..."
systemctl stop "$SERVICE_NAME" 2>/dev/null || true

# 移除不可变属性
chattr -i "$INSTALL_DIR/system_monitor" "$INSTALL_DIR/get_password" "$INSTALL_DIR/report_uninstall" "$INSTALL_DIR/uninstall.sh" "$CONFIG_FILE" "$SERVICE_FILE" 2>/dev/null || true

# 发送卸载消息
echo "Reporting uninstall to server..."
/opt/system_monitor/report_uninstall
if [ $? -ne 0 ]; then
    echo "Warning: Failed to report uninstall to server"
fi

# 删除文件和服务
echo "Removing files and service..."
rm -rf "$INSTALL_DIR" "$LOG_DIR" "$CACHE_DIR" "$SERVICE_FILE"
systemctl daemon-reload

echo "System Monitor uninstalled successfully"
exit 0