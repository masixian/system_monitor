# /opt/system_monitor/mq_service.py
import json
import logging
import os
from abc import ABC, abstractmethod

# RabbitMQ
import pika

# RocketMQ
from rocketmq.client import Producer, Message

logging.basicConfig(
    filename='/var/log/system_monitor/systemmonitor.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class MQService(ABC):
    @abstractmethod
    def send_message(self, message: dict) -> bool:
        pass

    def log_to_file(self, msg: str):
        logging.info(msg)


class RabbitMQService(MQService):
    def __init__(self, config: dict):
        self.config = config

    def send_message(self, message: dict) -> bool:
        connection = None
        try:
            # 每次发送前创建连接（短连接）
            credentials = pika.PlainCredentials(
                self.config['RabbitMQ']['Username'],
                self.config['RabbitMQ']['Password']
            )
            parameters = pika.ConnectionParameters(
                host=self.config['RabbitMQ']['Host'],
                port=self.config['RabbitMQ']['Port'],
                credentials=credentials,
                heartbeat=0,  # 短连接不需要心跳
                connection_attempts=3,
                retry_delay=2
            )
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            channel.queue_declare(queue=self.config['RabbitMQ']['QueueName'], durable=True)

            payload = json.dumps(message, ensure_ascii=False)
            self.log_to_file(f"RabbitMQ sending JSON: {payload}")

            channel.basic_publish(
                exchange='',
                routing_key=self.config['RabbitMQ']['QueueName'],
                body=payload.encode('utf-8'),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            self.log_to_file(f"RabbitMQ message sent successfully")
            return True
        except Exception as e:
            self.log_to_file(f"RabbitMQ send failed: {e}")
            return False
        finally:
            # 强制断开连接
            if connection and connection.is_open:
                try:
                    connection.close()
                except:
                    pass


class RocketMQService(MQService):
    def __init__(self, config: dict):
        self.config = config
        # 修复：临时修改 HOME
        os.environ['HOME'] = '/tmp'
        os.makedirs('/tmp/logs/rocketmq-cpp', exist_ok=True)

    def send_message(self, message: dict) -> bool:
        producer = None
        try:
            # 每次发送前创建 Producer（短连接）
            producer = Producer(self.config['RocketMQ']['GroupName'])
            producer.set_name_server_address(self.config['RocketMQ']['NameServerAddress'])
            producer.set_session_credentials(
                self.config['RocketMQ']['AccessKey'],
                self.config['RocketMQ']['SecretKey'],
                'public'
            )
            producer.start()

            msg = Message(self.config['RocketMQ']['Topic'])
            payload = json.dumps(message, ensure_ascii=False)
            msg.set_body(payload.encode('utf-8'))

            self.log_to_file(f"RocketMQ sending JSON: {payload}")

            ret = producer.send_sync(msg)
            if ret.status == 0:
                self.log_to_file(f"RocketMQ message sent: msg_id={ret.msg_id}")
                return True
            else:
                self.log_to_file(f"RocketMQ send failed: status={ret.status}")
                return False
        except Exception as e:
            self.log_to_file(f"RocketMQ send failed: {e}")
            return False
        finally:
            # 强制关闭 Producer
            if producer:
                try:
                    producer.shutdown()
                except:
                    pass


def create_mq_service(config: dict) -> MQService:
    mq_type = config.get("MQType", "RabbitMQ")
    if mq_type == "RocketMQ":
        return RocketMQService(config)
    else:
        return RabbitMQService(config)