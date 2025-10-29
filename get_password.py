#!/usr/bin/env python3
import sys
import json
import pika
import time
import netifaces
import os

def print_error(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)

def get_device_id():
    """返回带冒号的 MAC 地址：00:0c:29:b0:8d:55"""
    try:
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            if netifaces.AF_LINK in addrs:
                mac = addrs[netifaces.AF_LINK][0]['addr']
                if mac and mac != '00:00:00:00:00:00' and iface != 'lo':
                    if 'virtual' not in iface.lower() and 'vmware' not in iface.lower():
                        return mac  # 直接返回带冒号的格式
        return None
    except Exception as e:
        print_error(f"Error: 获取 MAC 地址失败: {e}")

def main(output_file):
    try:
        # 1. 加载配置
        config_path = '/opt/system_monitor/config.json'
        if not os.path.exists(config_path):
            print_error("Error: config.json 不存在")
        with open(config_path) as f:
            config = json.load(f)

        # 2. 获取带冒号的 MAC
        local_mac = get_device_id()
        if not local_mac:
            print_error("Error: 无法获取本机 MAC 地址")
        print(f"Debug: 本机 MAC (带冒号): {local_mac}", file=sys.stderr)

        # 3. 队列名：requirepass_queue_00:0c:29:b0:8d:55
        queue_name = f"requirepass_queue_{local_mac}"
        print(f"Debug: 监听队列: {queue_name}", file=sys.stderr)

        # 4. 轮询获取消息（5秒超时）
        password = None
        start_time = time.time()
        timeout_sec = 5

        while (time.time() - start_time) < timeout_sec:
            connection = None
            channel = None
            try:
                # 连接 RabbitMQ
                credentials = pika.PlainCredentials(config["RabbitMQ"]["Username"], config["RabbitMQ"]["Password"])
                connection = pika.BlockingConnection(
                    pika.ConnectionParameters(
                        host=config["RabbitMQ"]["Host"],
                        port=config["RabbitMQ"]["Port"],
                        credentials=credentials,
                        heartbeat=0,
                        connection_attempts=1
                    )
                )
                channel = connection.channel()

                # 声明 exchange 和队列
                channel.exchange_declare(exchange="requirepass_exchange", exchange_type='fanout', durable=True)
                channel.queue_declare(queue=queue_name, durable=True)
                channel.queue_bind(queue=queue_name, exchange="requirepass_exchange", routing_key="")

                # 轮询 basic_get
                method, properties, body = channel.basic_get(queue=queue_name, auto_ack=False)
                if method is None:
                    time.sleep(0.2)
                    continue

                # 解析消息
                message = body.decode('utf-8')
                print(f"Debug: 收到消息: {message}", file=sys.stderr)
                data = json.loads(message)

                # 关键：使用带冒号的 MAC 作为键
                if local_mac in data:
                    pwd = data[local_mac].get("password")
                    exp_time = data[local_mac].get("expirationTime")
                    if pwd and exp_time:
                        try:
                            exp_dt = time.strptime(exp_time, "%Y-%m-%d %H:%M:%S")
                            if time.mktime(exp_dt) > time.time():
                                password = pwd
                                # 保留消息
                                channel.basic_reject(method.delivery_tag, requeue=True)
                                print(f"Debug: 密码匹配成功: {pwd}", file=sys.stderr)
                                break
                            else:
                                channel.basic_reject(method.delivery_tag, requeue=False)
                                print("Debug: 密码已过期", file=sys.stderr)
                        except Exception as e:
                            channel.basic_reject(method.delivery_tag, requeue=False)
                            print(f"Debug: 时间解析失败: {e}", file=sys.stderr)
                    else:
                        channel.basic_reject(method.delivery_tag, requeue=False)
                else:
                    print(f"Debug: MAC 不匹配，期望: {local_mac}, 实际键: {list(data.keys())}", file=sys.stderr)
                    channel.basic_reject(method.delivery_tag, requeue=False)

            except Exception as e:
                print(f"Debug: 连接异常: {e}", file=sys.stderr)
                time.sleep(0.5)
            finally:
                if channel and channel.is_open:
                    try: channel.close()
                    except: pass
                if connection and connection.is_open:
                    try: connection.close()
                    except: pass

        # 5. 结果
        if not password:
            print_error("Error: 超时，未收到符合条件的密码消息")

        # 6. 写入文件
        with open(output_file, 'w') as f:
            f.write(password)
        os.chmod(output_file, 0o600)

    except Exception as e:
        print_error(f"Error: 未知错误: {e}")

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print_error("Usage: get_password <output_file>")
    main(sys.argv[1])