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

    @abstractmethod
    def close(self):
        pass

    def log_to_file(self, msg: str):
        logging.info(msg)


class RabbitMQService(MQService):
    def __init__(self, config: dict):
        self.config = config
        self.connection = None
        self.channel = None
        self._connect()

    def _connect(self):
        try:
            credentials = pika.PlainCredentials(
                self.config['RabbitMQ']['Username'],
                self.config['RabbitMQ']['Password']
            )
            parameters = pika.ConnectionParameters(
                host=self.config['RabbitMQ']['Host'],
                port=self.config['RabbitMQ']['Port'],
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            self.channel.queue_declare(queue=self.config['RabbitMQ']['QueueName'], durable=True)
            self.log_to_file("RabbitMQ connected successfully")
        except Exception as e:
            self.log_to_file(f"RabbitMQ connect failed: {e}")

    def send_message(self, message: dict) -> bool:
        try:
            if not self.channel or self.channel.is_closed:
                self._connect()
            payload = json.dumps(message, ensure_ascii=False)

            # 修复1：打印 RabbitMQ 发送的 JSON
            self.log_to_file(f"RabbitMQ sending JSON: {payload}")
            
            self.channel.basic_publish(
                exchange='',
                routing_key=self.config['RabbitMQ']['QueueName'],
                body=payload.encode('utf-8'),
                properties=pika.BasicProperties(delivery_mode=2)
            )

            self.log_to_file(f"RabbitMQ message sent: {message.get('Type', 'Unknown')}")
            return True
        except Exception as e:
            self.log_to_file(f"RabbitMQ send failed: {e}")
            return False

    def close(self):
        try:
            if self.connection and self.connection.is_open:
                self.connection.close()
                self.log_to_file("RabbitMQ connection closed")
        except Exception as e:
            self.log_to_file(f"RabbitMQ close error: {e}")


class RocketMQService(MQService):
    def __init__(self, config: dict):
        self.config = config
        self.producer = None
        
        # 终极修复：临时修改 HOME 环境变量，指向可写目录
        os.environ['HOME'] = '/tmp'  # 关键！C++ 客户端使用 $HOME/logs/rocketmq-cpp
        fake_home_log_dir = '/tmp/logs/rocketmq-cpp'
        os.makedirs(fake_home_log_dir, exist_ok=True)
        os.chmod(fake_home_log_dir, 0o777)  # 确保可写
        
        self._start_producer()

    def _start_producer(self):
        try:
            self.producer = Producer(self.config['RocketMQ']['GroupName'])
            self.producer.set_name_server_address(self.config['RocketMQ']['NameServerAddress'])
            self.producer.set_session_credentials(
                self.config['RocketMQ']['AccessKey'],
                self.config['RocketMQ']['SecretKey'],
                'public'  # channel 参数
            )
            self.producer.start()
            self.log_to_file("RocketMQ producer started")
        except Exception as e:
            self.log_to_file(f"RocketMQ start failed: {e}")

    def send_message(self, message: dict) -> bool:
        try:
            if not self.producer:
                self._start_producer()
            msg = Message(self.config['RocketMQ']['Topic'])
            payload = json.dumps(message, ensure_ascii=False)
            msg.set_body(payload.encode('utf-8'))
            
            # 修复1：打印完整 JSON
            self.log_to_file(f"RocketMQ sending JSON: {payload}")
            
            ret = self.producer.send_sync(msg)
            if ret.status == 0:
                self.log_to_file(f"RocketMQ message sent: msg_id={ret.msg_id}")
                return True
            else:
                self.log_to_file(f"RocketMQ send failed: status={ret.status}")
                return False
        except Exception as e:
            self.log_to_file(f"RocketMQ send failed: {e}")
            return False

    def close(self):
        try:
            if self.producer:
                self.producer.shutdown()
                self.log_to_file("RocketMQ producer shutdown")
        except Exception as e:
            self.log_to_file(f"RocketMQ shutdown error: {e}")


def create_mq_service(config: dict) -> MQService:
    mq_type = config.get("MQType", "RabbitMQ")
    if mq_type == "RocketMQ":
        return RocketMQService(config)
    else:
        return RabbitMQService(config)