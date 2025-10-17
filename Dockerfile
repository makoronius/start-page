FROM python:3.11-slim

# Install nginx and supervisor
RUN apt-get update && apt-get install -y \
    nginx \
    supervisor \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Setup Python backend
WORKDIR /app
COPY backend/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app.py /app/
COPY backend/auth.py /app/
# Note: config.yaml and users.yaml are mounted as volumes to preserve changes
# They should exist on the host before starting the container

# Create logs directory for audit logs
RUN mkdir -p /app/logs

# Setup nginx
COPY public/ /usr/share/nginx/html/
COPY scripts/ /scripts/

# Nginx configuration for proxying API requests
RUN echo 'server { \n\
    listen 80; \n\
    server_name _; \n\
    \n\
    location / { \n\
        root /usr/share/nginx/html; \n\
        index index.html; \n\
        try_files $uri $uri/ =404; \n\
        \n\
        # FORCE browsers to always fetch fresh HTML - no caching \n\
        add_header Cache-Control "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0"; \n\
        add_header Pragma "no-cache"; \n\
        add_header Expires "0"; \n\
        if_modified_since off; \n\
        etag off; \n\
    } \n\
    \n\
    location /api/ { \n\
        proxy_pass http://127.0.0.1:5555; \n\
        proxy_set_header Host $host; \n\
        proxy_set_header X-Real-IP $remote_addr; \n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; \n\
    } \n\
    \n\
    location /health { \n\
        proxy_pass http://127.0.0.1:5555/health; \n\
        proxy_set_header Host $host; \n\
        proxy_set_header X-Real-IP $remote_addr; \n\
    } \n\
}' > /etc/nginx/sites-available/default

# Supervisor configuration
RUN echo '[supervisord] \n\
nodaemon=true \n\
\n\
[program:nginx] \n\
command=/usr/sbin/nginx -g "daemon off;" \n\
autostart=true \n\
autorestart=true \n\
stdout_logfile=/dev/stdout \n\
stdout_logfile_maxbytes=0 \n\
stderr_logfile=/dev/stderr \n\
stderr_logfile_maxbytes=0 \n\
\n\
[program:backend] \n\
command=python /app/app.py \n\
directory=/app \n\
autostart=true \n\
autorestart=true \n\
stdout_logfile=/dev/stdout \n\
stdout_logfile_maxbytes=0 \n\
stderr_logfile=/dev/stderr \n\
stderr_logfile_maxbytes=0 \n\
' > /etc/supervisor/conf.d/supervisord.conf

EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/health || exit 1

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
