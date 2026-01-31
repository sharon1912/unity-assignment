"""
Unit tests for Customer Web Server
Tests API endpoints with mocked Kafka and external HTTP calls
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app():
    """Create test Flask app"""
    with patch('app.KafkaProducer'):
        from app import app
        app.config['TESTING'] = True
        yield app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


class TestHealthEndpoint:
    """Tests for /health endpoint"""

    def test_health_returns_200(self, client):
        response = client.get('/health')
        assert response.status_code == 200
        assert response.json['status'] == 'healthy'


class TestBuyEndpoint:
    """Tests for POST /buy endpoint"""

    def test_buy_missing_json_body(self, client):
        response = client.post('/buy', content_type='application/json')
        assert response.status_code == 400

    def test_buy_missing_required_fields(self, client):
        response = client.post('/buy', json={'username': 'test'})
        assert response.status_code == 400
        assert 'Missing required fields' in response.json['error']

    def test_buy_invalid_price_type(self, client):
        response = client.post('/buy', json={
            'username': 'test',
            'userid': 'user1',
            'price': 'not_a_number'
        })
        assert response.status_code == 400
        assert 'Price must be a valid number' in response.json['error']

    def test_buy_negative_price(self, client):
        response = client.post('/buy', json={
            'username': 'test',
            'userid': 'user1',
            'price': -10
        })
        assert response.status_code == 400
        assert 'Price cannot be negative' in response.json['error']

    @patch('app.get_kafka_producer')
    def test_buy_success(self, mock_producer, client):
        mock_future = MagicMock()
        mock_producer.return_value.send.return_value = mock_future

        response = client.post('/buy', json={
            'username': 'john',
            'userid': 'user123',
            'price': 29.99
        })

        assert response.status_code == 201
        assert response.json['status'] == 'success'
        assert response.json['data']['username'] == 'john'
        assert response.json['data']['userid'] == 'user123'
        assert response.json['data']['price'] == 29.99

    @patch('app.get_kafka_producer')
    def test_buy_kafka_error(self, mock_producer, client):
        from kafka.errors import KafkaError
        mock_producer.return_value.send.return_value.get.side_effect = KafkaError('Connection failed')

        response = client.post('/buy', json={
            'username': 'john',
            'userid': 'user123',
            'price': 29.99
        })

        assert response.status_code == 500


class TestGetAllUserBuysEndpoint:
    """Tests for GET /getAllUserBuys/<userid> endpoint"""

    @patch('app.requests.get')
    def test_get_user_buys_success(self, mock_get, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'userid': 'user123',
            'purchases': [{'price': 10}],
            'count': 1,
            'total_spent': 10
        }
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        response = client.get('/getAllUserBuys/user123')

        assert response.status_code == 200
        assert response.json['userid'] == 'user123'

    @patch('app.requests.get')
    def test_get_user_buys_timeout(self, mock_get, client):
        import requests
        mock_get.side_effect = requests.exceptions.Timeout()

        response = client.get('/getAllUserBuys/user123')

        assert response.status_code == 503

    @patch('app.requests.get')
    def test_get_user_buys_connection_error(self, mock_get, client):
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError()

        response = client.get('/getAllUserBuys/user123')

        assert response.status_code == 503
