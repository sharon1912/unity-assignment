# CI/CD Pipeline Documentation

This document describes the Continuous Integration and Continuous Deployment pipeline for the Customer Purchase System.

## Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Pull Request  │────▶│    CI: Tests    │────▶│  Merge to Main  │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Update Manifest │◀────│   Push Images   │◀────│  CD: Build      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Workflows

### CI - Continuous Integration (`ci.yml`)

**Trigger:** Pull requests to `main` branch

**Purpose:** Validate code changes before merging

**Steps:**
1. Checkout code
2. Build Docker images in test mode
3. Run pytest inside containers

```bash
# What runs internally:
make test
```

### CD - Continuous Deployment (`cd.yml`)

**Trigger:** Push to `main` branch

**Purpose:** Build, tag, and push production images to Docker Hub

**Steps:**
1. Checkout code
2. Read versions from `service-manifest.json`
3. Login to Docker Hub
4. Build and push all service images
5. Increment patch versions in manifest (1.0.0 → 1.0.1)
6. Commit updated manifest back to repository

## Version Management

Versions are stored in `service-manifest.json`:

```json
{
    "customer-management-api": {
        "version": "1.0.0"
    },
    "customer-web-server": {
        "version": "1.0.0"
    },
    "customer-ui": {
        "version": "1.0.0"
    }
}
```

After each successful CD run, the patch version is automatically incremented.

## Docker Images

### Image Naming Convention

```
sharonkurelovsky/sk-buy-app:<service>-v<version>
```

### Services

| Service | Image Tag Example |
|---------|-------------------|
| Web Server | `customer-web-server-v1.0.0` |
| Management API | `customer-management-api-v1.0.0` |
| UI | `customer-ui-v1.0.0` |

Each image also receives a `latest` tag.

## Multi-Stage Dockerfile

Each service uses a multi-stage Dockerfile with two targets:

| Target | Purpose | Includes Tests | Used By |
|--------|---------|----------------|---------|
| `test` | Testing | Yes | CI pipeline |
| `production` | Deployment | No | CD pipeline |

```bash
# Build test image
docker build --target test -t myapp:test .

# Build production image
docker build --target production -t myapp:prod .
```

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make test` | Build and run tests for all services |
| `make build` | Build production images for all services |
| `make test-web` | Test web server only |
| `make test-api` | Test management API only |
| `make build-web` | Build production web server image |
| `make build-api` | Build production management API image |
| `make push` | Push production images to registry |
| `make clean` | Remove test images |

## Required GitHub Secrets

Configure these in: Repository → Settings → Secrets → Actions

| Secret | Description |
|--------|-------------|
| `DOCKERHUB_USERNAME` | Docker Hub username |
| `DOCKERHUB_TOKEN` | Docker Hub access token |

### Creating a Docker Hub Access Token

1. Go to [hub.docker.com](https://hub.docker.com)
2. Account Settings → Security → New Access Token
3. Copy the token and add it as `DOCKERHUB_TOKEN` secret

## Local Development

### Running Tests Locally

```bash
# Test all services
make test

# Test specific service
make test-web
make test-api
```

### Building Production Images Locally

```bash
# Build all
make build

# Build with custom version
make build VERSION=v2.0.0

# Build specific service
make build-web
make build-api
```

## Pipeline Flow Example

1. Developer creates feature branch
2. Developer opens PR to `main`
3. **CI runs:** Tests execute in Docker containers
4. Tests pass → PR can be merged
5. PR merged to `main`
6. **CD runs:**
   - Reads `service-manifest.json` (version: 1.0.5)
   - Builds production images
   - Pushes `*-v1.0.5` and `*-latest` tags
   - Updates manifest to 1.0.6
   - Commits manifest change

## Troubleshooting

### CI Failures

1. Check test output in GitHub Actions logs
2. Run tests locally: `make test`
3. Check for dependency issues in `requirements.txt`

### CD Failures

1. Verify Docker Hub credentials are correct
2. Check if `service-manifest.json` is valid JSON
3. Ensure repository permissions allow pushing commits

### Skipping CD on Manifest Updates

The CD workflow uses `paths-ignore` and `[skip ci]` to prevent infinite loops when updating `service-manifest.json`.
