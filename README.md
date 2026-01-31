# Purchase Tracking System

A microservices-based purchase tracking system built with Python, Apache Kafka, and MongoDB, deployed on Kubernetes.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Components](#components)
3. [Code Structure](#code-structure)
4. [Docker Images](#docker-images)
5. [Kubernetes Deployment](#kubernetes-deployment)
6. [Monitoring & Observability](#monitoring--observability)
7. [Autoscaling](#autoscaling)
8. [Setup Instructions](#setup-instructions)
9. [Testing the System](#testing-the-system)
10. [API Reference](#api-reference)
11. [Troubleshooting](#troubleshooting)
12. [Cleanup](#cleanup)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              KUBERNETES CLUSTER                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                            namespace: purchase-system                        │
│                                                                             │
│  ┌─────────────────────┐         ┌─────────────────────────────────────┐   │
│  │  Customer Web       │         │  Customer Management API            │   │
│  │  Server             │         │                                     │   │
│  │  (Port 5000)        │         │  (Port 5001)                        │   │
│  │  /metrics ◄─────────┼─────────┼──────────────────► /metrics         │   │
│  │                     │         │  ┌─────────────────────────────┐   │   │
│  │  POST /buy ─────────┼─────────┼──► Kafka Consumer (Background) │   │   │
│  │         │           │  Kafka  │  │         │                   │   │   │
│  │         │           │ message │  │         ▼                   │   │   │
│  │         ▼           │         │  │  ┌─────────────┐            │   │   │
│  │  ┌───────────┐      │         │  │  │  MongoDB    │            │   │   │
│  │  │  Kafka    │      │         │  │  │  Write      │            │   │   │
│  │  │  Producer │      │         │  │  └─────────────┘            │   │   │
│  │  └───────────┘      │         │  └─────────────────────────────┘   │   │
│  │                     │         │                                     │   │
│  │  GET /getAllUser    │  HTTP   │  GET /purchases/{userid}           │   │
│  │  Buys/{userid} ─────┼─────────┼──►      │                          │   │
│  │         ▲           │         │         ▼                          │   │
│  │         │           │         │  ┌─────────────┐                   │   │
│  │         └───────────┼─────────┼──┤  MongoDB    │                   │   │
│  │                     │  JSON   │  │  Read       │                   │   │
│  │                     │         │  └─────────────┘                   │   │
│  │  HPA (2-10 pods)    │         │  HPA (1-5 pods)                    │   │
│  └─────────────────────┘         └─────────────────────────────────────┘   │
│           ▲                                                                 │
│           │ NodePort :30080                                                │
│           │                                                                 │
│  ┌────────┴────────┐              ┌─────────────┐    ┌─────────────────┐   │
│  │  External       │              │   Kafka     │    │    MongoDB      │   │
│  │  Traffic        │              │  (KRaft)    │    │  (StatefulSet)  │   │
│  └─────────────────┘              │  Port 9092  │    │   Port 27017    │   │
│                                   └─────────────┘    └─────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│                             namespace: monitoring                            │
│                                                                             │
│  ┌─────────────────────┐    ┌─────────────────────┐                        │
│  │  Prometheus         │    │  Prometheus         │                        │
│  │  Server             │───►│  Adapter            │──► Custom Metrics API  │
│  │  (scrapes /metrics) │    │  (exposes to HPA)   │                        │
│  └─────────────────────┘    └─────────────────────┘                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Buy Request Flow:**
   - User sends `POST /buy` to Customer Web Server
   - Web Server validates the request and adds a timestamp
   - Web Server publishes the purchase message to Kafka topic `purchases`
   - Returns success response to user immediately (async processing)

2. **Kafka Processing Flow:**
   - Customer Management API runs a background Kafka consumer
   - Consumer receives messages from `purchases` topic
   - Consumer writes each purchase document to MongoDB

3. **Query Flow:**
   - User sends `GET /getAllUserBuys/{userid}` to Customer Web Server
   - Web Server makes HTTP call to Customer Management API
   - Management API queries MongoDB for all purchases by userid
   - Results are returned through the chain to the user

---

## Components

### 1. Customer Web Server

**Purpose:** Customer-facing API gateway that handles incoming requests.

**Responsibilities:**
- Receive and validate purchase requests
- Publish purchase events to Kafka
- Proxy purchase queries to the Management API

**Technology:**
- Python 3.11
- Flask 3.0.0 (web framework)
- kafka-python-ng 2.2.2 (Kafka client)
- requests 2.31.0 (HTTP client)

### 2. Customer Management API

**Purpose:** Internal service that manages purchase data and Kafka consumption.

**Responsibilities:**
- Consume purchase messages from Kafka
- Store purchases in MongoDB
- Provide REST API for querying purchases

**Technology:**
- Python 3.12
- Flask 3.0.0 (web framework)
- kafka-python-ng 2.2.2 (Kafka client)
- pymongo 4.6.0 (MongoDB client)

### 3. Apache Kafka (KRaft Mode)

**Purpose:** Message broker for asynchronous communication.

**Why Kafka:**
- Decouples the web server from data storage
- Enables async processing (faster response times)
- Provides durability (messages persist until consumed)
- Allows scaling consumers independently

**KRaft Mode:**
- Modern Kafka deployment without Zookeeper
- Single process acts as both broker and controller
- Simpler configuration and faster startup

### 4. MongoDB

**Purpose:** Document database for storing purchase records.

**Why MongoDB:**
- Flexible schema for JSON-like documents
- Easy to query by userid
- Good performance for read-heavy workloads

**Schema:**
```json
{
  "username": "john_doe",
  "userid": "user123",
  "price": 29.99,
  "timestamp": "2024-01-15T10:30:00.123456"
}
```

---

## Code Structure

```
home-assigment/
├── README.md                              # This file
│
├── code/
│   ├── customer-web-server/
│   │   ├── app.py                         # Main Flask application + Prometheus metrics
│   │   ├── requirements.txt               # Python dependencies
│   │   └── Dockerfile                     # Container build instructions
│   │
│   └── customer-management-api/
│       ├── app.py                         # Flask app + Kafka consumer + Prometheus metrics
│       ├── requirements.txt               # Python dependencies
│       └── Dockerfile                     # Container build instructions
│
└── deployment/
    ├── namespace.yaml                     # Kubernetes namespace
    ├── AUTOSCALING.md                     # Detailed autoscaling documentation
    ├── database/
    │   └── mongodb.yaml                   # MongoDB StatefulSet + Service
    ├── kafka/
    │   └── kafka.yaml                     # Kafka Deployment + Service (KRaft)
    ├── customer-web-server/
    │   ├── deployment.yaml                # Web server Deployment + Prometheus annotations
    │   ├── service.yaml                   # Web server Service (NodePort)
    │   └── hpa.yaml                       # Horizontal Pod Autoscaler (2-10 pods)
    └── customer-management-api/
        ├── deployment.yaml                # Management API Deployment + Prometheus annotations
        ├── service.yaml                   # Management API Service (ClusterIP)
        └── hpa.yaml                       # Horizontal Pod Autoscaler (1-5 pods)
```

### Code Walkthrough

#### Customer Web Server (`code/customer-web-server/app.py`)

```python
# Key components explained:

# 1. Kafka Producer - Lazy initialization
#    Producer is created on first use, allowing the app to start
#    even if Kafka isn't ready yet
def get_kafka_producer():
    global _producer
    if _producer is None:
        _producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            retries=3
        )
    return _producer

# 2. POST /buy endpoint
#    - Validates required fields (username, userid, price)
#    - Adds timestamp
#    - Publishes to Kafka
#    - Returns immediately (async processing)
@app.route('/buy', methods=['POST'])
def buy():
    # ... validation ...
    purchase_message = {
        'username': data['username'],
        'userid': data['userid'],
        'price': float(data['price']),
        'timestamp': datetime.utcnow().isoformat()
    }
    producer.send(KAFKA_TOPIC, purchase_message)
    return jsonify({'status': 'success', ...}), 201

# 3. GET /getAllUserBuys endpoint
#    - Proxies request to Customer Management API
#    - Returns the response to the client
@app.route('/getAllUserBuys/<userid>', methods=['GET'])
def get_all_user_buys(userid):
    response = requests.get(f'{CUSTOMER_MGMT_API_URL}/purchases/{userid}')
    return jsonify(response.json()), response.status_code
```

#### Customer Management API (`code/customer-management-api/app.py`)

```python
# Key components explained:

# 1. MongoDB initialization with index
#    Index on 'userid' speeds up queries significantly
def init_mongodb():
    collection.create_index('userid')

# 2. Kafka Consumer - Runs in background thread
#    - Connects to Kafka with retry logic
#    - Processes messages in infinite loop
#    - Writes each message to MongoDB
def start_kafka_consumer():
    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=KAFKA_CONSUMER_GROUP,
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset='earliest'
    )
    for message in consumer:
        purchase_data = message.value
        collection.insert_one(purchase_data)

# 3. GET /purchases endpoint
#    - Queries MongoDB by userid
#    - Calculates total spent
#    - Returns purchases with summary
@app.route('/purchases/<userid>', methods=['GET'])
def get_purchases(userid):
    purchases = list(collection.find({'userid': userid}, {'_id': 0}))
    total_spent = sum(p.get('price', 0) for p in purchases)
    return jsonify({
        'userid': userid,
        'purchases': purchases,
        'count': len(purchases),
        'total_spent': round(total_spent, 2)
    })

# 4. Application startup
#    - Initialize MongoDB
#    - Start Kafka consumer in daemon thread
#    - Start Flask server
if __name__ == '__main__':
    init_mongodb()
    consumer_thread = threading.Thread(target=start_kafka_consumer, daemon=True)
    consumer_thread.start()
    app.run(host='0.0.0.0', port=5001)
```

---

## Docker Images

| Component | Image | Description |
|-----------|-------|-------------|
| Customer Web Server | `customer-web-server:latest` | Built locally from `code/customer-web-server/` |
| Customer Management API | `customer-management-api:latest` | Built locally from `code/customer-management-api/` |
| Kafka | `apache/kafka:latest` | Official Apache Kafka image with KRaft support |
| MongoDB | `mongo:7.0` | Official MongoDB image |

### Building Application Images

```bash
# Build Customer Web Server
docker build -t customer-web-server:latest ./code/customer-web-server

# Build Customer Management API
docker build -t customer-management-api:latest ./code/customer-management-api
```

### Dockerfile Explanation

Both application Dockerfiles follow the same pattern:

```dockerfile
# Use slim Python image for smaller size
FROM python:3.11-slim

WORKDIR /app

# Copy requirements first (layer caching optimization)
# If requirements don't change, this layer is cached
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose the Flask port
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]
```

---

## Kubernetes Deployment

### Namespace

All resources are deployed in the `purchase-system` namespace to isolate them from other workloads.

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: purchase-system
```

### Services

| Service | Type | Port | Description |
|---------|------|------|-------------|
| `customer-web-server` | NodePort | 80 → 30080 | External access for customers |
| `customer-management-api` | ClusterIP | 5001 | Internal only (called by web server) |
| `kafka` | ClusterIP | 9092 | Internal only (message broker) |
| `mongodb` | ClusterIP (Headless) | 27017 | Internal only (database) |

### Deployments

| Deployment | Replicas | Image | Purpose |
|------------|----------|-------|---------|
| `customer-web-server` | 2 | `customer-web-server:latest` | Handle customer requests |
| `customer-management-api` | 1 | `customer-management-api:latest` | Kafka consumer + API |
| `kafka` | 1 | `apache/kafka:latest` | Message broker |

### StatefulSet

| StatefulSet | Replicas | Image | Purpose |
|-------------|----------|-------|---------|
| `mongodb` | 1 | `mongo:7.0` | Persistent data storage |

### Key Configuration

#### Kafka Environment Variables (KRaft Mode)

```yaml
env:
  # KRaft mode - no Zookeeper needed
  - name: KAFKA_PROCESS_ROLES
    value: "broker,controller"
  - name: KAFKA_NODE_ID
    value: "1"
  - name: KAFKA_CONTROLLER_QUORUM_VOTERS
    value: "1@localhost:29093"

  # Listener configuration
  - name: KAFKA_LISTENERS
    value: "PLAINTEXT://0.0.0.0:29092,CONTROLLER://0.0.0.0:29093,PLAINTEXT_HOST://0.0.0.0:9092"
  - name: KAFKA_ADVERTISED_LISTENERS
    value: "PLAINTEXT://kafka:29092,PLAINTEXT_HOST://kafka:9092"

  # Single broker settings
  - name: KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR
    value: "1"

  # Required cluster ID for KRaft
  - name: CLUSTER_ID
    value: "MkU3OEVBNTcwNTJENDM2Qk"
```

#### Application Environment Variables

```yaml
# Customer Web Server
env:
  - name: KAFKA_BOOTSTRAP_SERVERS
    value: "kafka:9092"
  - name: KAFKA_TOPIC
    value: "purchases"
  - name: CUSTOMER_MGMT_API_URL
    value: "http://customer-management-api:5001"

# Customer Management API
env:
  - name: KAFKA_BOOTSTRAP_SERVERS
    value: "kafka:9092"
  - name: KAFKA_TOPIC
    value: "purchases"
  - name: KAFKA_CONSUMER_GROUP
    value: "purchase-consumer-group"
  - name: MONGODB_URI
    value: "mongodb://mongodb:27017"
  - name: MONGODB_DATABASE
    value: "purchase_db"
  - name: MONGODB_COLLECTION
    value: "purchases"
```

---

## Monitoring & Observability

The system includes Prometheus metrics for monitoring HTTP requests, latency, and Kafka message processing.

### Prometheus Stack

| Component | Namespace | Purpose |
|-----------|-----------|---------|
| Prometheus Server | `monitoring` | Scrapes and stores metrics |
| Prometheus Adapter | `monitoring` | Exposes metrics to Kubernetes HPA |
| Metrics Server | `kube-system` | Provides resource metrics (CPU/memory) |

### Exposed Metrics

Both services expose metrics at the `/metrics` endpoint using `prometheus-flask-exporter`.

| Metric | Type | Description |
|--------|------|-------------|
| `flask_http_request_total` | Counter | Total HTTP requests by method/status/path |
| `flask_http_request_duration_seconds` | Histogram | HTTP request latency distribution |
| `kafka_messages_processed_total` | Counter | Kafka messages processed (success/error) |
| `kafka_message_processing_seconds` | Histogram | Kafka message processing time |

### Prometheus Annotations

Deployments include annotations for automatic service discovery:

```yaml
annotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "5000"
  prometheus.io/path: "/metrics"
```

### Accessing Prometheus UI

```bash
kubectl port-forward svc/prometheus-server 9090:80 -n monitoring
# Open http://localhost:9090
```

### Example Queries

```promql
# Request rate per service
rate(flask_http_request_total[5m])

# 95th percentile latency
histogram_quantile(0.95, rate(flask_http_request_duration_seconds_bucket[5m]))

# Kafka processing rate
rate(kafka_messages_processed_total[5m])
```

---

## Autoscaling

The system uses Horizontal Pod Autoscalers (HPA) to automatically scale based on HTTP request rate.

### HPA Configuration

| Service | Min Pods | Max Pods | Scale Up Trigger |
|---------|----------|----------|------------------|
| customer-web-server | 2 | 10 | > 10 req/sec per pod |
| customer-management-api | 1 | 5 | > 10 req/sec per pod |

### How It Works

1. **Prometheus** scrapes `/metrics` from each pod
2. **Prometheus Adapter** exposes `flask_http_request_per_second` as a custom metric
3. **HPA** monitors the metric and scales pods accordingly

### Check HPA Status

```bash
kubectl get hpa -n purchase-system

# Expected output:
# NAME                          REFERENCE                            TARGETS   MINPODS   MAXPODS   REPLICAS
# customer-web-server-hpa       Deployment/customer-web-server       0/10      2         10        2
# customer-management-api-hpa   Deployment/customer-management-api   0/10      1         5         1
```

### Test Autoscaling

Generate load to trigger scaling:

```bash
# Install hey (load testing tool)
brew install hey

# Generate 1000 requests with 50 concurrent connections
hey -n 1000 -c 50 -m POST \
    -H "Content-Type: application/json" \
    -d '{"username":"loadtest","userid":"test","price":10}' \
    http://localhost:30080/buy

# Watch HPA react
kubectl get hpa -n purchase-system -w
```

### Scaling Behavior

**Scale Up:**
- Stabilization window: 30 seconds
- Can add up to 2 pods at a time or double the current count

**Scale Down:**
- Stabilization window: 5 minutes (prevents thrashing)
- Removes 1 pod at a time

For advanced autoscaling options (KEDA, custom metrics), see `deployment/AUTOSCALING.md`.

---

## Setup Instructions

### Prerequisites

- Docker Desktop (with Kubernetes enabled) or minikube/kind
- kubectl CLI configured
- curl (for testing)

### Step 1: Start Kubernetes

**Docker Desktop:**
- Open Docker Desktop → Settings → Kubernetes → Enable Kubernetes

**minikube:**
```bash
minikube start
eval $(minikube docker-env)  # Use minikube's Docker daemon
```

**kind:**
```bash
kind create cluster
```

### Step 2: Build Docker Images

```bash
cd home-assigment

# Build both images
docker build -t customer-web-server:latest ./code/customer-web-server
docker build -t customer-management-api:latest ./code/customer-management-api
```

**For kind users**, load images into the cluster:
```bash
kind load docker-image customer-web-server:latest
kind load docker-image customer-management-api:latest
```

### Step 3: Deploy to Kubernetes

```bash
# Create namespace
kubectl apply -f deployment/namespace.yaml

# Deploy MongoDB
kubectl apply -f deployment/database/mongodb.yaml

# Deploy Kafka (wait for it to be ready)
kubectl apply -f deployment/kafka/kafka.yaml
kubectl wait --for=condition=ready pod -l app=kafka -n purchase-system --timeout=120s

# Deploy applications
kubectl apply -f deployment/customer-management-api/
kubectl apply -f deployment/customer-web-server/

# Wait for all pods to be ready
kubectl wait --for=condition=ready pod -l app=customer-web-server -n purchase-system --timeout=60s
kubectl wait --for=condition=ready pod -l app=customer-management-api -n purchase-system --timeout=60s
```

### Step 4: Deploy Monitoring Stack (Optional but Recommended)

```bash
# Add Prometheus Helm repository
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install Prometheus
helm install prometheus prometheus-community/prometheus \
    --namespace monitoring \
    --create-namespace \
    --set server.persistentVolume.enabled=false \
    --set alertmanager.enabled=false

# Install Metrics Server (for resource metrics)
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# Patch for local Kubernetes (Docker Desktop/minikube)
kubectl patch deployment metrics-server -n kube-system --type='json' \
    -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--kubelet-insecure-tls"}]'

# Install Prometheus Adapter (for custom metrics HPA)
cat <<EOF | helm install prometheus-adapter prometheus-community/prometheus-adapter \
    --namespace monitoring -f -
prometheus:
  url: http://prometheus-server.monitoring.svc.cluster.local
  port: 80
rules:
  custom:
    - seriesQuery: 'flask_http_request_total{namespace!="",pod!=""}'
      resources:
        overrides:
          namespace: {resource: "namespace"}
          pod: {resource: "pod"}
      name:
        matches: "^(.*)_total$"
        as: "\${1}_per_second"
      metricsQuery: 'sum(rate(<<.Series>>{<<.LabelMatchers>>}[2m])) by (<<.GroupBy>>)'
EOF
```

### Step 5: Apply HPAs

```bash
kubectl apply -f deployment/customer-web-server/hpa.yaml
kubectl apply -f deployment/customer-management-api/hpa.yaml

# Verify HPAs
kubectl get hpa -n purchase-system
```

### Step 6: Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n purchase-system

# Expected output:
# NAME                                       READY   STATUS    RESTARTS   AGE
# customer-management-api-xxxxx              1/1     Running   0          1m
# customer-web-server-xxxxx                  1/1     Running   0          1m
# customer-web-server-yyyyy                  1/1     Running   0          1m
# kafka-xxxxx                                1/1     Running   0          2m
# mongodb-0                                  1/1     Running   0          2m

# Check services
kubectl get svc -n purchase-system

# Check monitoring pods
kubectl get pods -n monitoring
```

---

## Testing the System

### Access the API

The Customer Web Server is exposed on NodePort 30080:

```bash
# For Docker Desktop
curl http://localhost:30080/health

# For minikube
minikube service customer-web-server -n purchase-system --url
# Then use the URL provided
```

### Test 1: Create a Purchase

```bash
curl -X POST http://localhost:30080/buy \
  -H "Content-Type: application/json" \
  -d '{"username": "john", "userid": "user123", "price": 29.99}'
```

**Expected Response:**
```json
{
  "status": "success",
  "message": "Purchase recorded",
  "data": {
    "username": "john",
    "userid": "user123",
    "price": 29.99,
    "timestamp": "2024-01-15T10:30:00.123456"
  }
}
```

### Test 2: Get User Purchases

```bash
# Wait a moment for Kafka to process, then:
curl http://localhost:30080/getAllUserBuys/user123
```

**Expected Response:**
```json
{
  "userid": "user123",
  "purchases": [
    {
      "username": "john",
      "userid": "user123",
      "price": 29.99,
      "timestamp": "2024-01-15T10:30:00.123456"
    }
  ],
  "count": 1,
  "total_spent": 29.99
}
```

### Test 3: Multiple Purchases

```bash
# Add more purchases
curl -X POST http://localhost:30080/buy \
  -H "Content-Type: application/json" \
  -d '{"username": "john", "userid": "user123", "price": 15.50}'

curl -X POST http://localhost:30080/buy \
  -H "Content-Type: application/json" \
  -d '{"username": "john", "userid": "user123", "price": 42.00}'

# Check total
sleep 2
curl http://localhost:30080/getAllUserBuys/user123 | python3 -m json.tool
```

**Expected Response:**
```json
{
  "userid": "user123",
  "purchases": [
    {"username": "john", "userid": "user123", "price": 29.99, "timestamp": "..."},
    {"username": "john", "userid": "user123", "price": 15.50, "timestamp": "..."},
    {"username": "john", "userid": "user123", "price": 42.00, "timestamp": "..."}
  ],
  "count": 3,
  "total_spent": 87.49
}
```

### Test 4: Different Users

```bash
# Create purchase for different user
curl -X POST http://localhost:30080/buy \
  -H "Content-Type: application/json" \
  -d '{"username": "jane", "userid": "user456", "price": 99.99}'

# Query each user separately
curl http://localhost:30080/getAllUserBuys/user123
curl http://localhost:30080/getAllUserBuys/user456
```

### Test 5: Error Handling

```bash
# Missing required field
curl -X POST http://localhost:30080/buy \
  -H "Content-Type: application/json" \
  -d '{"username": "john"}'

# Expected: {"error": "Missing required fields: ['userid', 'price']"}

# Invalid price
curl -X POST http://localhost:30080/buy \
  -H "Content-Type: application/json" \
  -d '{"username": "john", "userid": "user123", "price": "invalid"}'

# Expected: {"error": "Price must be a valid number"}

# User with no purchases
curl http://localhost:30080/getAllUserBuys/nonexistent

# Expected: {"userid": "nonexistent", "purchases": [], "count": 0, "total_spent": 0}
```

### Test 6: Health Checks

```bash
# Customer Web Server health
curl http://localhost:30080/health
# Expected: {"status": "healthy"}

# Customer Management API health (via port-forward)
kubectl port-forward svc/customer-management-api 5001:5001 -n purchase-system &
curl http://localhost:5001/health
# Expected: {"status": "healthy", "mongodb": "connected"}
```

---

## API Reference

### Customer Web Server (Port 30080)

| Endpoint | Method | Description | Request Body | Response |
|----------|--------|-------------|--------------|----------|
| `/buy` | POST | Record a purchase | `{"username": "...", "userid": "...", "price": 0.00}` | `{"status": "success", "data": {...}}` |
| `/getAllUserBuys/{userid}` | GET | Get all user purchases | - | `{"userid": "...", "purchases": [...], "count": N, "total_spent": X.XX}` |
| `/health` | GET | Health check | - | `{"status": "healthy"}` |

### Customer Management API (Internal - Port 5001)

| Endpoint | Method | Description | Response |
|----------|--------|-------------|----------|
| `/purchases/{userid}` | GET | Query purchases from MongoDB | `{"userid": "...", "purchases": [...], "count": N, "total_spent": X.XX}` |
| `/health` | GET | Health check with MongoDB status | `{"status": "healthy", "mongodb": "connected"}` |

---

## Troubleshooting

### Check Pod Logs

```bash
# Customer Web Server logs
kubectl logs -f deployment/customer-web-server -n purchase-system

# Customer Management API logs (shows Kafka consumer activity)
kubectl logs -f deployment/customer-management-api -n purchase-system

# Kafka logs
kubectl logs -f deployment/kafka -n purchase-system
```

### Check Kafka Consumer

```bash
# Verify consumer is receiving messages
kubectl logs deployment/customer-management-api -n purchase-system | grep "Received purchase"
```

### Check MongoDB Data

```bash
# Connect to MongoDB and query data
kubectl exec -it mongodb-0 -n purchase-system -- mongosh purchase_db --eval "db.purchases.find()"

# Count documents
kubectl exec -it mongodb-0 -n purchase-system -- mongosh purchase_db --eval "db.purchases.countDocuments()"
```

### Common Issues

**1. Pods stuck in `ImagePullBackOff`:**
```bash
# Check if images exist locally
docker images | grep customer

# For minikube, ensure you're using minikube's Docker daemon
eval $(minikube docker-env)
docker build -t customer-web-server:latest ./code/customer-web-server
```

**2. Kafka connection errors:**
```bash
# Restart the application pods
kubectl rollout restart deployment/customer-management-api -n purchase-system
kubectl rollout restart deployment/customer-web-server -n purchase-system
```

**3. MongoDB connection errors:**
```bash
# Check MongoDB is running
kubectl get pods -n purchase-system -l app=mongodb

# Check MongoDB logs
kubectl logs mongodb-0 -n purchase-system
```

**4. Purchases not appearing in queries:**
```bash
# Check Kafka consumer logs for errors
kubectl logs deployment/customer-management-api -n purchase-system | tail -50

# Verify message was published
kubectl logs deployment/customer-web-server -n purchase-system | grep "Published purchase"
```

**5. HPA shows `<unknown>` targets:**
```bash
# Check if metrics-server is running
kubectl get pods -n kube-system | grep metrics-server

# Check if custom metrics API is available
kubectl get --raw /apis/custom.metrics.k8s.io/v1beta1 | head

# Verify Prometheus Adapter is running
kubectl get pods -n monitoring | grep prometheus-adapter

# Generate some traffic to populate metrics
curl -X POST http://localhost:30080/buy \
    -H "Content-Type: application/json" \
    -d '{"username":"test","userid":"test","price":10}'
```

**6. Prometheus not scraping targets:**
```bash
# Check Prometheus targets
kubectl port-forward svc/prometheus-server 9090:80 -n monitoring
# Open http://localhost:9090/targets

# Verify pod annotations
kubectl get pods -n purchase-system -o jsonpath='{.items[*].metadata.annotations}' | jq
```

---

## Cleanup

Remove all resources:

```bash
# Delete the entire namespace (removes all resources)
kubectl delete namespace purchase-system

# Remove local Docker images (optional)
docker rmi customer-web-server:latest customer-management-api:latest
```

---

## Configuration Reference

### Environment Variables

| Variable | Service | Default | Description |
|----------|---------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | Both | `kafka:9092` | Kafka broker address |
| `KAFKA_TOPIC` | Both | `purchases` | Kafka topic for purchase events |
| `CUSTOMER_MGMT_API_URL` | Web Server | `http://customer-management-api:5001` | Management API URL |
| `KAFKA_CONSUMER_GROUP` | Mgmt API | `purchase-consumer-group` | Kafka consumer group ID |
| `MONGODB_URI` | Mgmt API | `mongodb://mongodb:27017` | MongoDB connection string |
| `MONGODB_DATABASE` | Mgmt API | `purchase_db` | MongoDB database name |
| `MONGODB_COLLECTION` | Mgmt API | `purchases` | MongoDB collection name |

---

## Future Improvements

- [ ] Add authentication/authorization (JWT tokens)
- [x] Add Prometheus metrics endpoints
- [ ] Add structured logging with correlation IDs
- [ ] Use Helm charts for easier deployment
- [x] Add horizontal pod autoscaling
- [ ] Add MongoDB authentication
- [ ] Add Kafka Schema Registry for message validation
- [ ] Add integration tests
- [ ] Add CI/CD pipeline
- [ ] Add Grafana dashboards for visualization
- [ ] Add alerting rules for Prometheus
