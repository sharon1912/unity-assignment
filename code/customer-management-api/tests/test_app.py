"""
Unit tests for Customer Management API
Tests API endpoints with mocked MongoDB and Kafka
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app():
    """Create test Flask app with mocked dependencies"""
    with patch('app.KafkaConsumer'), \
         patch('app.MongoClient') as mock_mongo:

        # Setup mock MongoDB
        mock_collection = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_mongo.return_value.__getitem__ = MagicMock(return_value=mock_db)

        from app import app
        app.config['TESTING'] = True
        yield app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


class TestHealthEndpoint:
    """Tests for /health endpoint"""

    @patch('app.mongo_client')
    def test_health_mongodb_connected(self, mock_client, client):
        mock_client.admin.command.return_value = True

        response = client.get('/health')

        assert response.status_code == 200
        assert response.json['status'] == 'healthy'
        assert response.json['mongodb'] == 'connected'

    @patch('app.mongo_client')
    def test_health_mongodb_disconnected(self, mock_client, client):
        from pymongo.errors import ConnectionFailure
        mock_client.admin.command.side_effect = ConnectionFailure('Connection lost')

        response = client.get('/health')

        assert response.status_code == 500
        assert response.json['status'] == 'unhealthy'


class TestGetPurchasesEndpoint:
    """Tests for GET /purchases/<userid> endpoint"""

    @patch('app.collection')
    def test_get_purchases_success(self, mock_collection, client):
        mock_collection.find.return_value = [
            {'userid': 'user123', 'price': 10.00, 'username': 'john'},
            {'userid': 'user123', 'price': 20.00, 'username': 'john'}
        ]

        response = client.get('/purchases/user123')

        assert response.status_code == 200
        assert response.json['userid'] == 'user123'
        assert response.json['count'] == 2
        assert response.json['total_spent'] == 30.00

    @patch('app.collection')
    def test_get_purchases_not_found(self, mock_collection, client):
        mock_collection.find.return_value = []

        response = client.get('/purchases/nonexistent')

        assert response.status_code == 404
        assert response.json['count'] == 0
        assert response.json['purchases'] == []

    @patch('app.collection')
    def test_get_purchases_database_error(self, mock_collection, client):
        mock_collection.find.side_effect = Exception('Database error')

        response = client.get('/purchases/user123')

        assert response.status_code == 500
        assert 'Database error' in response.json['error']
