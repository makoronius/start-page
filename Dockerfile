FROM nginx:alpine

# Copy static files
COPY public/ /usr/share/nginx/html/

# Copy scripts to a volume mount point
COPY scripts/ /scripts/

# Expose port 80
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
