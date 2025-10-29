#!/usr/bin/env python3
import sys
import json
import pika
import time
import netifaces
import os
from datetime import datetime

def print_error(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)

def get_local_mac():
    """返回带冒号的 MAC 地址：00:0c:29:b0:8d:55"""
    try:
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            if netifaces.AF_LINK in addrs:
                mac = addrs[netifaces.AF_LINK][0]['addr']
                if mac and mac != '00:00:00:00:00:00' and iface != 'lo':
                    if 'virtual' not in iface.lower() and 'vmware' not in iface.lower():
                        return mac
        return None
    except Exception as e:
        print_error(f"Error: 获取 MAC 地址失败: {e}")

def main(password):
    try:
        # 1. 加载配置
        config_path = '/opt/system_monitor/config.json'
        if not os.path.exists(config_path):
            print_error("Error: config.json 不存在")
        with open(config_path) as f:
            config = json.load(f)

        # 2. 获取 MAC
        local_mac = get_local_mac()
        if not local_mac:
            print_error("Error: 无法获取本机 MAC 地址")

        # 3. 构建卸载事件
        uninstall_event = {
            "mac": local_mac,
            "uninstallTime": datetime.now().strftime("%Y-%m-%d %H:%m:%S")
        }
        json_str = json.dumps(uninstall_event, ensure_ascii=False)
        print(f"卸载事件已上报: {json_str}")

        # 4. 连接 RabbitMQ
        credentials = pika.PlainCredentials(config["RabbitMQ"]["Username"], config["RabbitMQ"]["Password"])
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=config["RabbitMQ"]["Host"],
                port=config["RabbitMQ"]["Port"],
                credentials=credentials,
                heartbeat=0
            )
        )
        channel = connection.channel()

        # 5. 声明 exchange 和队列
        exchange = "ClientUninstall"
        queue = "ClientUninstallQueue"
        routing_key = "uninstall"

        channel.exchange_declare(exchange=exchange, exchange_type='direct', durable=True)
        channel.queue_declare(queue=queue, durable=True, exclusive=False, auto_delete=False)
        channel.queue_bind(queue=queue, exchange=exchange, routing_key=routing_key)

        # 6. 发送消息
        body = json_str.encode('utf-8')
        properties = pika.BasicProperties(delivery_mode=2)  # 持久化
        channel.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=body,
            properties=properties
        )

        channel.close()
        connection.close()

    except Exception as e:
        print_error(f"Error: 上报卸载事件失败 - {e}")

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print_error("Usage: report_uninstall <password>")
    main(sys.argv[1])