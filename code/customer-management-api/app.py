"""
Customer Management API
=======================
This service provides:
- REST API endpoint to query purchases from MongoDB
- Background Kafka consumer that stores incoming purchases

The Kafka consumer runs in a separate thread and continuously listens
for purchase messages, storing them in MongoDB for later retrieval.
"""

import os
import json
import logging
import threading
import time

from flask import Flask, jsonify
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from prometheus_flask_exporter import PrometheusMetrics
from prometheus_client import Counter, Histogram

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment variables
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'purchases')
KAFKA_CONSUMER_GROUP = os.getenv('KAFKA_CONSUMER_GROUP', 'purchase-consumer-group')
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://mongodb:27017')
MONGODB_DATABASE = os.getenv('MONGODB_DATABASE', 'purchase_db')
MONGODB_COLLECTION = os.getenv('MONGODB_COLLECTION', 'purchases')

app = Flask(__name__)

# Initialize Prometheus metrics for HTTP endpoints
metrics = PrometheusMetrics(app)
metrics.info('app_info', 'Customer Management API', version='1.0.0')

# Custom Prometheus metrics for Kafka consumer
kafka_messages_processed = Counter(
    'kafka_messages_processed_total',
    'Total Kafka messages processed',
    ['status']
)
kafka_processing_time = Histogram(
    'kafka_message_processing_seconds',
    'Time spent processing Kafka messages'
)

# MongoDB connection (global for Flask routes)
mongo_client = None
db = None
collection = None


def init_mongodb():
    """
    Initialize MongoDB connection and create index on userid.
    Called at startup.
    """
    global mongo_client, db, collection

    logger.info(f"Connecting to MongoDB at {MONGODB_URI}")
    mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    db = mongo_client[MONGODB_DATABASE]
    collection = db[MONGODB_COLLECTION]

    # Create index on userid for faster queries
    collection.create_index('userid')
    logger.info("MongoDB connection established, index created on 'userid'")


def start_kafka_consumer():
    """
    Kafka consumer loop that runs in a background thread.
    Consumes purchase messages from Kafka and stores them in MongoDB.
    """
    logger.info(f"Starting Kafka consumer for topic '{KAFKA_TOPIC}'")
    logger.info(f"Consumer group: {KAFKA_CONSUMER_GROUP}")

    # Retry loop for Kafka connection (Kafka may not be ready immediately)
    consumer = None
    while consumer is None:
        try:
            consumer = KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                group_id=KAFKA_CONSUMER_GROUP,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                auto_offset_reset='earliest',
                enable_auto_commit=True,
                consumer_timeout_ms=-1  # Wait indefinitely for messages
            )
            logger.info("Kafka consumer connected successfully")
        except KafkaError as e:
            logger.warning(f"Kafka not ready, retrying in 5s: {e}")
            time.sleep(5)

    # Process messages indefinitely
    for message in consumer:
        start_time = time.time()
        try:
            purchase_data = message.value
            logger.info(f"Received purchase: userid={purchase_data.get('userid')}, price={purchase_data.get('price')}")

            # Insert into MongoDB
            result = collection.insert_one(purchase_data)
            logger.info(f"Stored in MongoDB with ID: {result.inserted_id}")

            # Record success metrics
            kafka_messages_processed.labels(status='success').inc()

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            kafka_messages_processed.labels(status='error').inc()
            # Continue processing other messages even if one fails
        finally:
            # Record processing time
            kafka_processing_time.observe(time.time() - start_time)


@app.route('/purchases/<userid>', methods=['GET'])
def get_purchases(userid):
    """
    GET /purchases/<userid>
    -----------------------
    Retrieves all purchases for a specific user from MongoDB.

    Args:
        userid: The user's unique identifier

    Returns:
        200: JSON with list of purchases, count, and total spent
        404: No purchases found for user
        500: Database error
    """
    try:
        # Query MongoDB for all purchases by this user
        # Exclude the MongoDB _id field from response
        purchases = list(collection.find(
            {'userid': userid},
            {'_id': 0}
        ))

        if not purchases:
            return jsonify({
                'userid': userid,
                'purchases': [],
                'count': 0,
                'total_spent': 0
            }), 404

        # Calculate total spent
        total_spent = sum(p.get('price', 0) for p in purchases)

        return jsonify({
            'userid': userid,
            'purchases': purchases,
            'count': len(purchases),
            'total_spent': round(total_spent, 2)
        }), 200

    except Exception as e:
        logger.error(f"Error querying purchases for user {userid}: {str(e)}")
        return jsonify({'error': f'Database error: {str(e)}'}), 500


@app.route('/health', methods=['GET'])
def health():
    """
    GET /health
    -----------
    Health check endpoint for Kubernetes probes.
    Verifies MongoDB connection is alive.
    """
    try:
        # Ping MongoDB to verify connection
        mongo_client.admin.command('ping')
        return jsonify({'status': 'healthy', 'mongodb': 'connected'}), 200
    except ConnectionFailure:
        return jsonify({'status': 'unhealthy', 'mongodb': 'disconnected'}), 500
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500


if __name__ == '__main__':
    # Initialize MongoDB connection
    init_mongodb()

    # Start Kafka consumer in background thread
    # daemon=True ensures thread stops when main program exits
    consumer_thread = threading.Thread(target=start_kafka_consumer, daemon=True)
    consumer_thread.start()
    logger.info("Kafka consumer thread started")

    # Start Flask API server
    logger.info("Starting Customer Management API on port 5001")
    app.run(host='0.0.0.0', port=5001, debug=False)
