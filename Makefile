# Makefile for Customer Application
# Usage:
#   make test          - Build and run tests for all services
#   make build         - Build production images for all services
#   make test-web      - Build and run tests for web server only
#   make test-api      - Build and run tests for management API only
#   make build-web     - Build production image for web server
#   make build-api     - Build production image for management API

DOCKER_REGISTRY ?= sharonkurelovsky/sk-buy-app
VERSION ?= latest

# Service paths
WEB_SERVER_PATH = code/customer-web-server
MGMT_API_PATH = code/customer-management-api

# Image names
WEB_SERVER_IMAGE = $(DOCKER_REGISTRY):customer-web-server-$(VERSION)
MGMT_API_IMAGE = $(DOCKER_REGISTRY):customer-management-api-$(VERSION)

.PHONY: all test build test-web test-api build-web build-api clean

# ============ Test Targets ============

test: test-web test-api
	@echo "All tests completed"

test-web:
	@echo "Building and testing customer-web-server..."
	docker build --target test -t customer-web-server:test ./$(WEB_SERVER_PATH)
	docker run --rm customer-web-server:test

test-api:
	@echo "Building and testing customer-management-api..."
	docker build --target test -t customer-management-api:test ./$(MGMT_API_PATH)
	docker run --rm customer-management-api:test

# ============ Production Build Targets ============

build: build-web build-api
	@echo "All production images built"

build-web:
	@echo "Building production image for customer-web-server..."
	docker build --target production -t $(WEB_SERVER_IMAGE) ./$(WEB_SERVER_PATH)
	@echo "Built: $(WEB_SERVER_IMAGE)"

build-api:
	@echo "Building production image for customer-management-api..."
	docker build --target production -t $(MGMT_API_IMAGE) ./$(MGMT_API_PATH)
	@echo "Built: $(MGMT_API_IMAGE)"

# ============ Push Targets ============

push: push-web push-api
	@echo "All images pushed"

push-web: build-web
	docker push $(WEB_SERVER_IMAGE)

push-api: build-api
	docker push $(MGMT_API_IMAGE)

# ============ Clean ============

clean:
	@echo "Removing test images..."
	-docker rmi customer-web-server:test 2>/dev/null
	-docker rmi customer-management-api:test 2>/dev/null
