# /opt/system_monitor/kafka_service.py
import json
import logging
from kafka import KafkaProducer

logging.basicConfig(
    filename='/var/log/system_monitor/systemmonitor.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class KafkaService:
    def __init__(self, config: dict):
        self.config = config
        self.producer = None

    def _get_producer(self):
        """每次发送前创建连接（短连接）"""
        if self.producer is None:
            try:
                # 自动判断是否启用 SASL_PLAINTEXT
                username = self.config['Kafka'].get('Username', '')
                password = self.config['Kafka'].get('Password', '')

                if username and password:
                    # 启用 SASL_PLAINTEXT 认证
                    producer_kwargs = {
                        'bootstrap_servers': self.config['Kafka']['BootstrapServers'],
                        'security_protocol': 'SASL_PLAINTEXT',
                        'sasl_mechanism': 'PLAIN',
                        'sasl_plain_username': username,
                        'sasl_plain_password': password,
                        'retries': 3,
                        'linger_ms': 5,
                        'acks': 'all'
                    }
                    logging.info("Kafka Producer created with SASL_PLAINTEXT authentication")
                else:
                    # 无认证模式
                    producer_kwargs = {
                        'bootstrap_servers': self.config['Kafka']['BootstrapServers'],
                        'retries': 3,
                        'linger_ms': 5,
                        'acks': 'all'
                    }
                    logging.info("Kafka Producer created (no authentication)")

                self.producer = KafkaProducer(**producer_kwargs)

            except Exception as e:
                logging.error(f"Kafka Producer init failed: {e}")
                raise

        return self.producer

    def send_message(self, message: dict) -> bool:
        try:
            producer = self._get_producer()
            topic = self.config['Kafka']['Topic']
            payload = json.dumps(message, ensure_ascii=False).encode('utf-8')

            logging.info(f"Kafka sending JSON: {json.dumps(message, ensure_ascii=False)}")

            future = producer.send(topic, value=payload)
            record_metadata = future.get(timeout=10)

            logging.info(f"Kafka message sent successfully | topic={topic} | partition={record_metadata.partition} | offset={record_metadata.offset}")
            return True

        except Exception as e:
            logging.error(f"Kafka send failed: {e}")
            return False

        finally:
            # 短连接：发送完立即关闭
            if self.producer:
                try:
                    self.producer.close(timeout=5)
                    self.producer = None
                    logging.info("Kafka Producer closed")
                except Exception as e:
                    logging.warning(f"Kafka Producer close failed: {e}")

    def close(self):
        # 保留接口兼容性
        if self.producer:
            try:
                self.producer.close()
            except:
                pass