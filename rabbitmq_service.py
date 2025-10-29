import pika
import json
import logging
import time
import os

logging.basicConfig(filename='/var/log/system_monitor/systemmonitor.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class RabbitMQService:
    def __init__(self, config):
        self.host = config["RabbitMQ"]["Host"]
        self.port = int(config["RabbitMQ"]["Port"])
        self.username = config["RabbitMQ"]["Username"]
        self.password = config["RabbitMQ"]["Password"]
        self.queue_name = config["RabbitMQ"]["QueueName"]
        self.log_file_path = config["Logging"]["LogFilePath"]
        self.connection = None
        self.channel = None
        self._is_initialized = False
        os.makedirs(os.path.dirname(self.log_file_path), exist_ok=True)
        self.initialize_with_retry()

    def initialize_with_retry(self, max_retries=20, retry_interval=20):
        retry_count = 0
        while not self._is_initialized and retry_count < max_retries:
            try:
                retry_count += 1
                logging.info(f"Attempting to connect to RabbitMQ (Attempt {retry_count}, Host: {self.host}:{self.port})")
                credentials = pika.PlainCredentials(self.username, self.password)
                self.connection = pika.BlockingConnection(
                    pika.ConnectionParameters(
                        host=self.host,
                        port=self.port,
                        credentials=credentials,
                        heartbeat=3600,
                        blocked_connection_timeout=1200,
                        socket_timeout=60
                    )
                )
                self.channel = self.connection.channel()
                self.channel.queue_declare(queue=self.queue_name, durable=True)
                self._is_initialized = True
                logging.info(f"RabbitMQ initialized successfully (Attempt {retry_count})")
            except Exception as e:
                logging.error(f"RabbitMQ connection failed: {e}")
                if retry_count < max_retries:
                    time.sleep(retry_interval)
                else:
                    logging.error("Max retries reached, failed to connect to RabbitMQ")
                    raise

    def send_message(self, message):
        if not self._is_initialized or not self.channel or self.channel.is_closed:
            logging.error("Cannot send message: RabbitMQ not initialized or channel closed")
            self._is_initialized = False
            self.initialize_with_retry()
            if not self._is_initialized:
                return False
        try:
            body = json.dumps(message, ensure_ascii=False).encode('utf-8')
            self.channel.basic_publish(
                exchange='',
                routing_key=self.queue_name,
                body=body,
                properties=pika.BasicProperties(delivery_mode=2)
            )
            logging.info(f"Message sent to RabbitMQ: {json.dumps(message, ensure_ascii=False)}")
            return True
        except Exception as e:
            logging.error(f"Failed to send message: {e}")
            self._is_initialized = False
            return False

    def close(self):
        try:
            if self.channel and not self.channel.is_closed:
                self.channel.close()
            if self.connection and not self.connection.is_closed:
                self.connection.close()
            self._is_initialized = False
            logging.info("RabbitMQ connection closed")
        except Exception as e:
            logging.error(f"Failed to close RabbitMQ: {e}")