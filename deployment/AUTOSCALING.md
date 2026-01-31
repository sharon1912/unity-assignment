# Autoscaling Guide

This guide explains how to configure autoscaling for the Purchase Tracking System based on HTTP request metrics and other relevant indicators.

## Overview

The system supports two levels of autoscaling:

1. **Basic (CPU/Memory)** - Built into Kubernetes, works out of the box
2. **Advanced (HTTP Metrics)** - Requires Prometheus + Prometheus Adapter

## Quick Start: CPU-Based Autoscaling

### Prerequisites

Ensure metrics-server is installed (required for HPA):

```bash
# Check if metrics-server is running
kubectl get deployment metrics-server -n kube-system

# If not installed (Docker Desktop usually has it):
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

### Deploy HPAs

```bash
# Deploy HPA for Customer Web Server
kubectl apply -f deployment/customer-web-server/hpa.yaml

# Deploy HPA for Customer Management API
kubectl apply -f deployment/customer-management-api/hpa.yaml

# Verify HPAs are created
kubectl get hpa -n purchase-system
```

### HPA Configuration

**Customer Web Server HPA:**
| Setting | Value | Reason |
|---------|-------|--------|
| minReplicas | 2 | High availability |
| maxReplicas | 10 | Cost control |
| CPU target | 70% | Scale before saturation |
| Memory target | 80% | Secondary trigger |
| Scale up delay | 30s | React quickly to load |
| Scale down delay | 300s | Avoid thrashing |

**Customer Management API HPA:**
| Setting | Value | Reason |
|---------|-------|--------|
| minReplicas | 1 | Single consumer default |
| maxReplicas | 5 | Limited by Kafka partitions |
| CPU target | 70% | Scale before saturation |
| Scale up delay | 60s | More conservative |
| Scale down delay | 300s | Avoid thrashing |

### Monitor Autoscaling

```bash
# Watch HPA status
kubectl get hpa -n purchase-system -w

# Check current replicas vs desired
kubectl describe hpa customer-web-server-hpa -n purchase-system
```

### Test Autoscaling

Generate load to trigger scaling:

```bash
# Install hey (HTTP load generator)
# macOS: brew install hey
# Linux: go install github.com/rakyll/hey@latest

# Generate load (1000 requests, 50 concurrent)
hey -n 1000 -c 50 -m POST \
    -H "Content-Type: application/json" \
    -d '{"username":"test","userid":"loadtest","price":10}' \
    http://localhost:30080/buy

# Watch pods scale up
kubectl get pods -n purchase-system -w
```

---

## Advanced: HTTP Request-Based Autoscaling

For autoscaling based on actual HTTP requests per second, you need:

1. **Prometheus** - Collects metrics from pods
2. **Prometheus Adapter** - Exposes metrics to Kubernetes HPA

### Step 1: Install Prometheus

```bash
# Add Prometheus Helm repo
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install Prometheus
helm install prometheus prometheus-community/prometheus \
    --namespace monitoring \
    --create-namespace \
    --set server.persistentVolume.enabled=false \
    --set alertmanager.enabled=false
```

### Step 2: Install Prometheus Adapter

```bash
# Install Prometheus Adapter
helm install prometheus-adapter prometheus-community/prometheus-adapter \
    --namespace monitoring \
    --set prometheus.url=http://prometheus-server.monitoring.svc \
    --set prometheus.port=80
```

### Step 3: Configure Custom Metrics HPA

Create HPA that scales based on HTTP requests per second:

```yaml
# deployment/customer-web-server/hpa-http.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: customer-web-server-hpa-http
  namespace: purchase-system
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: customer-web-server
  minReplicas: 2
  maxReplicas: 10
  metrics:
    # Scale based on HTTP requests per second per pod
    - type: Pods
      pods:
        metric:
          name: flask_http_request_total
        target:
          type: AverageValue
          averageValue: "100"  # Scale when > 100 req/s per pod
```

### Step 4: Prometheus Adapter Configuration

Add rules to convert Flask metrics to Kubernetes metrics:

```yaml
# prometheus-adapter-config.yaml
rules:
  - seriesQuery: 'flask_http_request_total{namespace!="",pod!=""}'
    resources:
      overrides:
        namespace: {resource: "namespace"}
        pod: {resource: "pod"}
    name:
      matches: "^(.*)_total$"
      as: "${1}_per_second"
    metricsQuery: 'rate(<<.Series>>{<<.LabelMatchers>>}[2m])'
```

---

## Metrics Exposed

### Customer Web Server (`/metrics`)

| Metric | Type | Description |
|--------|------|-------------|
| `flask_http_request_total` | Counter | Total HTTP requests by method, status, path |
| `flask_http_request_duration_seconds` | Histogram | Request latency distribution |
| `flask_http_request_created` | Gauge | Request creation timestamp |

### Customer Management API (`/metrics`)

| Metric | Type | Description |
|--------|------|-------------|
| `flask_http_request_total` | Counter | Total HTTP requests |
| `flask_http_request_duration_seconds` | Histogram | Request latency |
| `kafka_messages_processed_total` | Counter | Kafka messages processed (success/error) |
| `kafka_message_processing_seconds` | Histogram | Kafka message processing time |

### Useful Queries

```promql
# HTTP requests per second (Web Server)
rate(flask_http_request_total{app="customer-web-server"}[5m])

# Average request latency
histogram_quantile(0.95, rate(flask_http_request_duration_seconds_bucket[5m]))

# Kafka consumer throughput
rate(kafka_messages_processed_total{status="success"}[5m])

# Error rate
rate(flask_http_request_total{status=~"5.."}[5m]) / rate(flask_http_request_total[5m])
```

---

## Alternative: KEDA (Kubernetes Event-Driven Autoscaling)

KEDA provides more sophisticated autoscaling triggers including Kafka lag:

### Install KEDA

```bash
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm install keda kedacore/keda --namespace keda --create-namespace
```

### Scale Based on Kafka Lag

```yaml
# Scale Customer Management API based on Kafka consumer lag
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: customer-management-api-scaler
  namespace: purchase-system
spec:
  scaleTargetRef:
    name: customer-management-api
  minReplicaCount: 1
  maxReplicaCount: 5
  triggers:
    - type: kafka
      metadata:
        bootstrapServers: kafka:9092
        consumerGroup: purchase-consumer-group
        topic: purchases
        lagThreshold: "100"  # Scale when lag > 100 messages
```

---

## Summary

| Approach | Complexity | Metrics | Best For |
|----------|------------|---------|----------|
| CPU/Memory HPA | Low | Built-in | Simple workloads |
| Prometheus + Adapter | Medium | HTTP req/s, latency | API services |
| KEDA | Medium | Kafka lag, custom | Event-driven services |

**Recommendation:** Start with CPU-based HPA (already configured), then add Prometheus for HTTP metrics visibility, and consider KEDA for Kafka-based scaling.
