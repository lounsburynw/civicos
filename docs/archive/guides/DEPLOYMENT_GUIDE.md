# Civic Engagement Platform - Deployment Guide

## Overview

This guide covers production deployment of the Civic Engagement Platform, including security hardening, performance optimization, and monitoring setup for the conversational civic participation system.

## Pre-Deployment Checklist

### ✅ Security Requirements
- [ ] OpenAI API key secured in environment variables
- [ ] Production API keys generated (replace `dev_key_local`)
- [ ] HTTPS/SSL certificate configured
- [ ] CORS origins restricted to production domains
- [ ] Rate limiting configured and tested
- [ ] XSS protection validated with security test suite
- [ ] Input validation active for all endpoints

### ✅ Data Requirements
- [ ] Fresh civic data generated with `python src/civic_digest.py schema [url]`
- [ ] Data freshness within 7 days of deployment
- [ ] All required civic opportunity JSON files present in `data/schema/`
- [ ] Contact information verified for accuracy
- [ ] Meeting dates and times confirmed with city websites

### ✅ Testing Requirements
- [ ] All integration tests passing (`python tests/test_all_fixes.py`)
- [ ] Security tests validated (`python tests/test_action_security.py`)
- [ ] Action button functionality verified (`python tests/test_action_buttons.py`)
- [ ] Frontend-backend integration tested
- [ ] Load testing completed for expected user volume

## Environment Setup

### Production Environment Variables
```bash
# Required - API Keys
export OPENAI_API_KEY="sk-your-production-openai-key"
export CIVIC_WEB_KEY="your-secure-32-character-production-key"

# Required - Server Configuration  
export PORT=8001
export FLASK_ENV=production
export DEBUG=false

# Security Configuration
export CORS_ORIGINS="https://your-civic-domain.com,https://www.your-civic-domain.com"
export RATE_LIMIT_REQUESTS=100
export RATE_LIMIT_WINDOW=3600

# Data Configuration
export DATA_DIRECTORY="/app/data/schema"
export MAX_MESSAGE_LENGTH=1000
export LOG_LEVEL=INFO

# Optional - Performance Tuning
export GUNICORN_WORKERS=4
export GUNICORN_THREADS=2
export GUNICORN_TIMEOUT=30
```

### Development Environment Variables
```bash
# Development/Testing
export OPENAI_API_KEY="your-development-key"
export CIVIC_WEB_KEY="dev_key_local"
export PORT=8001
export DEBUG=true
export CORS_ORIGINS="http://localhost:3000,http://localhost:8000"
export DATA_DIRECTORY="data/schema"
export LOG_LEVEL=DEBUG
```

## Deployment Options

### Option 1: Direct Server Deployment (Production)

#### System Requirements
- **OS**: Ubuntu 20.04+ or CentOS 8+
- **Python**: 3.8+
- **Memory**: 2GB minimum, 4GB recommended
- **Storage**: 10GB minimum (for logs and data)
- **Network**: HTTPS/SSL certificate required

#### Installation Steps
```bash
# 1. Create deployment user
sudo useradd -m -s /bin/bash civic-app
sudo usermod -aG sudo civic-app
su - civic-app

# 2. Clone repository
git clone https://github.com/your-org/civic-engagement-platform.git /home/civic-app/civic
cd /home/civic-app/civic

# 3. Install Python dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Set environment variables
sudo cp deployment/civic.env /etc/environment
# Edit /etc/environment with your production values

# 5. Generate fresh civic data
source venv/bin/activate
python src/civic_digest.py schema "https://www.cityofsanrafael.org/meetings/"

# 6. Run integration tests
python tests/test_all_fixes.py
python tests/test_action_security.py

# 7. Configure systemd service
sudo cp deployment/civic-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable civic-api
sudo systemctl start civic-api

# 8. Configure nginx reverse proxy
sudo cp deployment/civic-nginx.conf /etc/nginx/sites-available/civic
sudo ln -s /etc/nginx/sites-available/civic /etc/nginx/sites-enabled/
sudo systemctl restart nginx
```

#### Systemd Service Configuration
```ini
# /etc/systemd/system/civic-api.service
[Unit]
Description=Civic Engagement Platform API
After=network.target

[Service]
Type=simple
User=civic-app
WorkingDirectory=/home/civic-app/civic
Environment=PATH=/home/civic-app/civic/venv/bin
ExecStart=/home/civic-app/civic/venv/bin/python src/civic_api_integrated.py
Restart=always
RestartSec=10

# Environment variables
EnvironmentFile=/etc/environment

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/home/civic-app/civic/output

[Install]
WantedBy=multi-user.target
```

#### Nginx Reverse Proxy Configuration
```nginx
# /etc/nginx/sites-available/civic
server {
    listen 80;
    server_name your-civic-domain.com www.your-civic-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-civic-domain.com www.your-civic-domain.com;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/your-civic-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-civic-domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Security Headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';";

    # Rate Limiting
    limit_req_zone $binary_remote_addr zone=civic:10m rate=10r/s;
    limit_req zone=civic burst=20 nodelay;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }

    # Static files (if any)
    location /static/ {
        alias /home/civic-app/civic/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Health check endpoint
    location /health {
        proxy_pass http://127.0.0.1:8001/health;
        access_log off;
    }
}
```

### Option 2: Docker Deployment

#### Dockerfile
```dockerfile
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY data/ ./data/
COPY tests/ ./tests/

# Create non-root user
RUN useradd -m -u 1001 civic && chown -R civic:civic /app
USER civic

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Expose port
EXPOSE 8001

# Start application
CMD ["python", "src/civic_api_integrated.py"]
```

#### Docker Compose Configuration
```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  civic-api:
    build: .
    ports:
      - "8001:8001"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - CIVIC_WEB_KEY=${CIVIC_WEB_KEY}
      - FLASK_ENV=production
      - DEBUG=false
      - CORS_ORIGINS=${CORS_ORIGINS}
      - LOG_LEVEL=INFO
    volumes:
      - ./output:/app/output:ro
      - ./logs:/app/logs:rw
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./deployment/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/ssl/certs:ro
    depends_on:
      - civic-api
    restart: unless-stopped
```

#### Deploy with Docker
```bash
# 1. Create production environment file
cat > .env.prod << EOF
OPENAI_API_KEY=your-production-key
CIVIC_WEB_KEY=your-production-api-key
CORS_ORIGINS=https://your-civic-domain.com
EOF

# 2. Build and start services
docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d

# 3. Check health
docker-compose -f docker-compose.prod.yml ps
curl https://your-civic-domain.com/health
```

### Option 3: Cloud Platform Deployment (Heroku)

#### Heroku Setup
```bash
# 1. Install Heroku CLI and login
heroku login

# 2. Create Heroku app
heroku create your-civic-app-name

# 3. Set environment variables
heroku config:set OPENAI_API_KEY=your-key
heroku config:set CIVIC_WEB_KEY=your-production-key
heroku config:set FLASK_ENV=production
heroku config:set DEBUG=false

# 4. Deploy
git push heroku main

# 5. Verify deployment
heroku logs --tail
curl https://your-civic-app-name.herokuapp.com/health
```

#### Procfile
```
web: python src/civic_api_integrated.py
```

#### requirements.txt
```
Flask==2.3.2
requests==2.31.0
openai==1.3.0
gunicorn==21.2.0
```

## Data Pipeline Setup

### Automated Data Refresh

#### Cron Job Configuration
```bash
# Add to crontab (crontab -e)
# Refresh civic data every Monday at 9 AM
0 9 * * 1 cd /home/civic-app/civic && /home/civic-app/civic/venv/bin/python src/civic_digest.py schema "https://www.cityofsanrafael.org/meetings/" >> /var/log/civic-refresh.log 2>&1

# Daily data staleness check
0 6 * * * cd /home/civic-app/civic && /home/civic-app/civic/venv/bin/python scripts/check_data_freshness.py >> /var/log/civic-freshness.log 2>&1
```

#### Data Refresh Script
```python
#!/usr/bin/env python3
# scripts/check_data_freshness.py

import json
import os
from datetime import datetime, timedelta

def check_data_freshness():
    """Check if civic data needs refresh"""
    data_dir = os.environ.get('DATA_DIRECTORY', 'data/schema')
    staleness_days = int(os.environ.get('DATA_STALENESS_DAYS', '7'))
    
    now = datetime.now()
    refresh_needed = False
    
    for filename in os.listdir(data_dir):
        if filename.endswith('.json'):
            file_path = os.path.join(data_dir, filename)
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            created_at = datetime.fromisoformat(
                data.get('created_at', '').replace('Z', '+00:00')
            )
            
            age_days = (now - created_at.replace(tzinfo=None)).days
            
            if age_days > staleness_days:
                print(f"STALE DATA: {filename} is {age_days} days old")
                refresh_needed = True
    
    if refresh_needed:
        print("Data refresh recommended")
        return 1
    else:
        print("Data is fresh")
        return 0

if __name__ == '__main__':
    exit(check_data_freshness())
```

### Multi-City Data Management

```bash
# Generate data for multiple cities
python src/civic_digest.py schema "https://www.cityofsanrafael.org/meetings/" --city san-rafael
python src/civic_digest.py schema "https://www.berkeley.ca.us/meetings/" --city berkeley
python src/civic_digest.py schema "https://www.paloalto.ca.us/meetings/" --city palo-alto
```

## Monitoring & Observability

### Application Logging

#### Structured Logging Configuration
```python
# Add to src/civic_api_integrated.py
import logging
import json
from datetime import datetime

class StructuredLogger:
    def __init__(self, name):
        self.logger = logging.getLogger(name)
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def log_request(self, endpoint, method, user_id, processing_time):
        self.logger.info(json.dumps({
            'event': 'api_request',
            'endpoint': endpoint,
            'method': method,
            'user_id': user_id,
            'processing_time_ms': processing_time,
            'timestamp': datetime.utcnow().isoformat()
        }))
    
    def log_action_generated(self, action_type, opportunity_id, user_interests):
        self.logger.info(json.dumps({
            'event': 'action_generated',
            'action_type': action_type,
            'opportunity_id': opportunity_id,
            'user_interests': user_interests,
            'timestamp': datetime.utcnow().isoformat()
        }))
```

### Health Monitoring

#### Health Check Endpoint Enhancement
```python
@app.route('/health')
def health_check():
    """Enhanced health check with dependency validation"""
    checks = {
        'api_server': True,
        'openai_connection': check_openai_connection(),
        'civic_data': check_civic_data_availability(),
        'disk_space': check_disk_space(),
        'memory_usage': check_memory_usage()
    }
    
    all_healthy = all(checks.values())
    status_code = 200 if all_healthy else 503
    
    return jsonify({
        'status': 'healthy' if all_healthy else 'unhealthy',
        'timestamp': datetime.utcnow().isoformat(),
        'checks': checks,
        'version': '1.0.0'
    }), status_code
```

### Performance Metrics

#### Key Metrics to Monitor
```bash
# 1. API Response Times
curl -w "@curl-format.txt" -s -o /dev/null https://your-civic-domain.com/api/conversation

# 2. Error Rates
grep "ERROR" /var/log/civic-api.log | wc -l

# 3. Memory Usage
ps aux | grep python | grep civic

# 4. Disk Usage
df -h /home/civic-app/civic/

# 5. Active Connections
netstat -an | grep :8001 | grep ESTABLISHED | wc -l
```

#### curl-format.txt
```
     time_namelookup:  %{time_namelookup}s\n
        time_connect:  %{time_connect}s\n
     time_appconnect:  %{time_appconnect}s\n
    time_pretransfer:  %{time_pretransfer}s\n
       time_redirect:  %{time_redirect}s\n
  time_starttransfer:  %{time_starttransfer}s\n
                     ----------\n
          time_total:  %{time_total}s\n
```

## Security Hardening

### SSL/TLS Configuration

#### Let's Encrypt SSL Setup
```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Generate SSL certificate
sudo certbot --nginx -d your-civic-domain.com -d www.your-civic-domain.com

# Auto-renewal
sudo crontab -e
# Add: 0 12 * * * /usr/bin/certbot renew --quiet
```

### Firewall Configuration

```bash
# UFW Firewall Setup
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'
sudo ufw --force enable

# Check status
sudo ufw status verbose
```

### API Security Best Practices

#### Rate Limiting Enhancement
```python
# Enhanced rate limiting with Redis
import redis
from datetime import datetime, timedelta

class AdvancedRateLimiter:
    def __init__(self, redis_client):
        self.redis = redis_client
    
    def allow_request(self, client_id, limit=100, window=3600):
        """Token bucket rate limiting with Redis"""
        now = datetime.now().timestamp()
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(client_id, 0, now - window)
        pipe.zcard(client_id)
        pipe.zadd(client_id, {str(now): now})
        pipe.expire(client_id, window)
        results = pipe.execute()
        
        request_count = results[1]
        return request_count < limit
```

#### Input Validation Enhancement
```python
from marshmallow import Schema, fields, validate

class ConversationRequestSchema(Schema):
    message = fields.Str(required=True, validate=validate.Length(min=1, max=1000))
    city = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    state = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    county = fields.Str(missing=None, validate=validate.Length(max=100))
    interests = fields.List(fields.Str(), missing=[])

# Usage in API endpoint
schema = ConversationRequestSchema()
try:
    data = schema.load(request.get_json())
except ValidationError as err:
    return jsonify({'error': 'Invalid request', 'details': err.messages}), 400
```

## Backup & Recovery

### Data Backup Strategy

```bash
#!/bin/bash
# scripts/backup_civic_data.sh

BACKUP_DIR="/home/civic-app/backups"
DATE=$(date +%Y%m%d_%H%M%S)
SOURCE_DIR="/home/civic-app/civic/output"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup civic data
tar -czf "$BACKUP_DIR/civic_data_$DATE.tar.gz" "$SOURCE_DIR"

# Keep only last 7 days of backups
find "$BACKUP_DIR" -name "civic_data_*.tar.gz" -mtime +7 -delete

# Upload to cloud storage (optional)
# aws s3 cp "$BACKUP_DIR/civic_data_$DATE.tar.gz" s3://your-backup-bucket/

echo "Backup completed: civic_data_$DATE.tar.gz"
```

### Disaster Recovery Plan

1. **Data Recovery**: Restore from daily backups
2. **Service Recovery**: Restart with systemd or Docker
3. **Configuration Recovery**: Version-controlled deployment scripts
4. **Key Rotation**: Environment variable updates

```bash
# Quick recovery commands
# 1. Stop services
sudo systemctl stop civic-api nginx

# 2. Restore data
tar -xzf /home/civic-app/backups/civic_data_latest.tar.gz -C /

# 3. Update configurations
sudo cp /home/civic-app/civic/deployment/civic-nginx.conf /etc/nginx/sites-available/civic

# 4. Restart services
sudo systemctl start civic-api nginx

# 5. Verify health
curl https://your-civic-domain.com/health
```

## Troubleshooting

### Common Issues

#### 1. API Server Won't Start
```bash
# Check logs
sudo journalctl -u civic-api -f

# Verify environment variables
sudo -u civic-app printenv | grep -E "(OPENAI|CIVIC|FLASK)"

# Test Python environment
sudo -u civic-app /home/civic-app/civic/venv/bin/python -c "import flask, openai, requests; print('Dependencies OK')"
```

#### 2. Action Buttons Not Working
```bash
# Test action generation endpoint
curl -X POST http://localhost:8001/api/conversation \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev_key_local" \
  -d '{"message": "housing opportunities", "city": "San Rafael", "state": "California", "interests": ["housing"]}'

# Check civic data files
ls -la data/schema/
head -20 data/schema/newsletter_*.json
```

#### 3. High Memory Usage
```bash
# Monitor memory usage
top -p $(pgrep -f civic_api)

# Check for memory leaks
valgrind --tool=memcheck --leak-check=full python src/civic_api_integrated.py

# Restart service if needed
sudo systemctl restart civic-api
```

#### 4. SSL Certificate Issues
```bash
# Check certificate status
sudo certbot certificates

# Test SSL configuration
ssllabs-scan --grade --quiet your-civic-domain.com

# Renew certificate
sudo certbot renew --dry-run
```

### Log Analysis

```bash
# Error analysis
grep -i error /var/log/civic-api.log | tail -20

# Performance analysis
grep "processing_time" /var/log/civic-api.log | awk '{print $NF}' | sort -n | tail -10

# User activity analysis
grep "api_request" /var/log/civic-api.log | jq '.endpoint' | sort | uniq -c
```

## Performance Optimization

### Production Tuning

#### Gunicorn Configuration
```python
# gunicorn_config.py
bind = "127.0.0.1:8001"
workers = 4
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
timeout = 30
keepalive = 2
preload_app = True
```

#### Start with Gunicorn
```bash
gunicorn --config gunicorn_config.py src.civic_api_integrated:app
```

#### Caching Strategy
```python
from functools import lru_cache
import hashlib

class ResponseCache:
    def __init__(self, max_size=1000, ttl=3600):
        self.cache = {}
        self.ttl = ttl
    
    def get_cache_key(self, message, interests):
        data = f"{message}:{':'.join(sorted(interests))}"
        return hashlib.md5(data.encode()).hexdigest()
    
    def get(self, key):
        if key in self.cache:
            cached_time, response = self.cache[key]
            if time.time() - cached_time < self.ttl:
                return response
            del self.cache[key]
        return None
    
    def set(self, key, response):
        self.cache[key] = (time.time(), response)
```

## Cost Monitoring

### OpenAI API Cost Tracking

```python
class CostTracker:
    def __init__(self):
        self.daily_costs = defaultdict(float)
    
    def track_request(self, tokens_used, model="gpt-4"):
        # GPT-4 pricing: $0.03/1K tokens input, $0.06/1K tokens output
        cost_per_token = 0.00006 if model == "gpt-4" else 0.000002
        request_cost = tokens_used * cost_per_token
        
        today = datetime.now().date()
        self.daily_costs[today] += request_cost
        
        # Alert if daily cost exceeds threshold
        if self.daily_costs[today] > 50.0:  # $50/day threshold
            self.send_cost_alert(today, self.daily_costs[today])
    
    def send_cost_alert(self, date, cost):
        # Send alert via email/Slack/etc.
        print(f"COST ALERT: Daily OpenAI usage exceeded ${cost:.2f} on {date}")
```

## Scaling Considerations

### Horizontal Scaling

#### Load Balancer Configuration (nginx)
```nginx
upstream civic_app {
    server 127.0.0.1:8001 weight=1;
    server 127.0.0.1:8002 weight=1;
    server 127.0.0.1:8003 weight=1;
}

server {
    listen 443 ssl;
    server_name your-civic-domain.com;
    
    location / {
        proxy_pass http://civic_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

#### Multi-Instance Deployment
```bash
# Start multiple instances
for port in 8001 8002 8003; do
    PORT=$port gunicorn --bind 127.0.0.1:$port src.civic_api_integrated:app &
done
```

### Database Migration (Future)

When scaling beyond file-based storage:

```sql
-- PostgreSQL schema for civic opportunities
CREATE TABLE civic_opportunities (
    id VARCHAR(255) PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    when_scheduled TIMESTAMP WITH TIME ZONE,
    deadline TIMESTAMP WITH TIME ZONE,
    engagement_info TEXT,
    impact_summary TEXT,
    source_url TEXT,
    location VARCHAR(255),
    meeting_type VARCHAR(100),
    project_type VARCHAR(100),
    engagement_tier VARCHAR(50),
    contact_email VARCHAR(255),
    contact_name VARCHAR(255),
    contact_phone VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    scraped_from TEXT
);

CREATE INDEX idx_project_type ON civic_opportunities(project_type);
CREATE INDEX idx_when_scheduled ON civic_opportunities(when_scheduled);
CREATE INDEX idx_location ON civic_opportunities(location);
```

---

*Deployment Guide Version 1.0*  
*Last Updated: September 8, 2025*  
*Next Review: September 22, 2025*

**Support**: For deployment issues, contact the development team or create an issue in the repository.