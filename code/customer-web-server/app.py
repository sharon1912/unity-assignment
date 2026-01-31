"""
Customer Facing Web Server
==========================
This service handles customer-facing API endpoints:
- POST /buy: Receives purchase data and publishes to Kafka
- GET /getAllUserBuys/<userid>: Fetches all purchases for a user from the Customer Management API
- GET /health: Health check endpoint for Kubernetes probes

The service acts as the entry point for customers, forwarding purchase events
to Kafka for asynchronous processing by the Customer Management API.
"""

import os
import json
import logging
from datetime import datetime

from flask import Flask, request, jsonify
from kafka import KafkaProducer
from kafka.errors import KafkaError
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment variables with sensible defaults
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'purchases')
CUSTOMER_MGMT_API_URL = os.getenv('CUSTOMER_MGMT_API_URL', 'http://customer-management-api:5001')

app = Flask(__name__)

# Global Kafka producer instance (lazy initialization)
_producer = None


def get_kafka_producer():
    """
    Returns a singleton Kafka producer instance.
    Uses lazy initialization to handle startup before Kafka is ready.
    """
    global _producer
    if _producer is None:
        logger.info(f"Connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS}")
        _producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            retries=3,
            retry_backoff_ms=1000
        )
    return _producer


@app.route('/buy', methods=['POST'])
def buy():
    """
    POST /buy
    ---------
    Handles purchase requests from customers.

    Expected JSON body:
    {
        "username": "john_doe",
        "userid": "user123",
        "price": 29.99
    }

    The endpoint adds a timestamp and publishes the purchase to Kafka.

    Returns:
        201: Purchase recorded successfully
        400: Missing required fields or invalid data
        500: Failed to publish to Kafka
    """
    # Parse JSON body
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body must be JSON'}), 400

    # Validate required fields
    required_fields = ['username', 'userid', 'price']
    missing_fields = [f for f in required_fields if f not in data]
    if missing_fields:
        return jsonify({'error': f'Missing required fields: {missing_fields}'}), 400

    # Validate price is a number
    try:
        price = float(data['price'])
        if price < 0:
            return jsonify({'error': 'Price cannot be negative'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': 'Price must be a valid number'}), 400

    # Build purchase message with timestamp
    purchase_message = {
        'username': str(data['username']),
        'userid': str(data['userid']),
        'price': price,
        'timestamp': datetime.utcnow().isoformat()
    }

    # Publish to Kafka
    try:
        producer = get_kafka_producer()
        future = producer.send(KAFKA_TOPIC, purchase_message)
        # Wait for the message to be sent (with timeout)
        future.get(timeout=10)
        logger.info(f"Published purchase for user {purchase_message['userid']}")

        return jsonify({
            'status': 'success',
            'message': 'Purchase recorded',
            'data': purchase_message
        }), 201

    except KafkaError as e:
        logger.error(f"Kafka error: {str(e)}")
        return jsonify({'error': 'Failed to record purchase - messaging system unavailable'}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({'error': f'Failed to record purchase: {str(e)}'}), 500


@app.route('/getAllUserBuys/<userid>', methods=['GET'])
def get_all_user_buys(userid):
    """
    GET /getAllUserBuys/<userid>
    ----------------------------
    Retrieves all purchases for a specific user by calling the Customer Management API.

    Args:
        userid: The user's unique identifier

    Returns:
        200: JSON with list of purchases and summary
        404: User not found or no purchases
        503: Customer Management API unavailable
    """
    try:
        # Call Customer Management API
        response = requests.get(
            f'{CUSTOMER_MGMT_API_URL}/purchases/{userid}',
            timeout=10
        )

        # Forward the response from Customer Management API
        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        logger.error(f"Timeout calling Customer Management API for user {userid}")
        return jsonify({'error': 'Service timeout - please try again'}), 503
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error to Customer Management API")
        return jsonify({'error': 'Service unavailable'}), 503
    except Exception as e:
        logger.error(f"Error fetching purchases for user {userid}: {str(e)}")
        return jsonify({'error': f'Failed to fetch purchases: {str(e)}'}), 500


@app.route('/health', methods=['GET'])
def health():
    """
    GET /health
    -----------
    Health check endpoint for Kubernetes liveness/readiness probes.
    Returns healthy if the service is running.
    """
    return jsonify({'status': 'healthy'}), 200


if __name__ == '__main__':
    # Run Flask development server
    # In production, use gunicorn or similar WSGI server
    logger.info("Starting Customer Web Server on port 5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
