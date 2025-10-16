# Start Page - Local Services Dashboard

A clean, modern landing page for quick access to all your local development services.

![Dashboard Preview](docs/screenshot.png)

## Features

- 🎨 Modern, responsive design with Dark/Light/System theme switcher
- 🔗 Quick links to all services (local and remote)
- ⚙️ Web-based configuration editor
- 📝 Dynamic service management via Config tab
- 📄 CSV generation from configuration for port proxy scripts
- 🌐 Flask API backend for configuration management
- 🔧 Port proxy management scripts included
- 🐳 Docker-ready deployment
- ⚡ Auto-refresh every 5 minutes
- 💾 Theme preferences stored in browser cookies

## Services Included

| Service | Port | Description |
|---------|------|-------------|
| **Start Page** | 80 | This dashboard |
| **Whisper Transcriber** | 5001 | GPU-accelerated transcription |
| **Gitea** | 3000 | Self-hosted Git server |
| **Portainer** | 9443 | Docker management UI |
| **Webhook Server** | 9000 | CI/CD automation |

## Quick Start

### Local Development

Open `public/index.html` in your browser.

### Docker Deployment

```bash
docker compose up -d
```

Access at: `http://localhost`

### Production Deployment (on remote server)

```bash
# Clone repository
git clone http://100.79.70.15:3000/mark/start-page.git /opt/start-page

# Build and run
cd /opt/start-page
docker compose up -d
```

Access at: `http://100.79.70.15`

## Port Proxy Scripts

This project includes Windows port proxy management scripts for exposing WSL2 services to the network.

### Files

- `scripts/Update-DockerPortProxy.ps1` - PowerShell script
- `scripts/port-mappings.csv` - Port configuration

### Usage

On Windows (as Administrator):

```powershell
cd C:\Scripts
.\Update-DockerPortProxy.ps1
```

### Adding New Services

1. Edit `scripts/port-mappings.csv`:
   ```csv
   Port,Service,Description
   8080,My App,My new application
   ```

2. Run the PowerShell script to apply changes

3. Update `public/index.html` to add the new service card

## Project Structure

```
start-page/
├── public/
│   └── index.html          # Landing page with Config tab
├── backend/
│   ├── app.py              # Flask API server
│   └── requirements.txt    # Python dependencies
├── scripts/
│   └── Update-DockerPortProxy.ps1
├── config.yaml             # Central configuration file
├── docs/
│   └── README.md
├── docker-compose.yml
├── Dockerfile
└── README.md
```

## Configuration

### Web-Based Configuration

Access the **Config** tab in the web interface to:
- Add, edit, or remove services
- Change service icons, names, URLs, and descriptions
- Mark services as local (included in CSV export)
- Download generated CSV for port proxy scripts

All changes are stored in `config.yaml`.

### Manual Configuration

Edit `config.yaml` to configure:

**Settings:**
- `hostname`: Server hostname (e.g., "hypervisor")
- `title`: Dashboard title
- `subtitle`: Dashboard subtitle
- `auto_refresh_minutes`: Auto-refresh interval
- `ssh_user`: SSH username

**Services:**
```yaml
services:
  - name: "Service Name"
    icon: "🔧"
    url: "http://hostname:port"
    description: "Service description"
    port: 8080
    local: true
    status: running
```

**Port Mappings:**
```yaml
port_mappings:
  - port: 8080
    service: "Service Name"
    description: "Service description"
```

### Theme Customization

Users can switch between Light, Dark, and System themes using the theme switcher in the top-right corner. Theme preference is saved in browser cookies.

## Automatic Deployment

This project is set up for automatic deployment via Gitea webhooks:

1. Push to main branch → Triggers webhook
2. Deployment script pulls latest code
3. Docker containers rebuild and restart

## Port Proxy Management

The included PowerShell script manages Windows port proxies for WSL2:

**Features:**
- CSV-based configuration
- Automatic WSL IP detection
- Firewall rule creation
- Service URL display

**Run after:**
- WSL restart
- Windows reboot
- Adding new services

## Health Checks

The Docker container includes a health check that verifies the web server is responding.

Check health:
```bash
docker inspect --format='{{.State.Health.Status}}' start-page
```

## Troubleshooting

### Page not accessible

1. Check if container is running:
   ```bash
   docker ps | grep start-page
   ```

2. Check port 80 is not in use:
   ```bash
   netstat -an | grep :80
   ```

3. Verify port proxy (Windows):
   ```powershell
   netsh interface portproxy show v4tov4
   ```

### WSL2 services not accessible from network

Run the port proxy script on Windows as Administrator:
```powershell
C:\Scripts\Update-DockerPortProxy.ps1
```

## License

MIT License

## Author

Mark Emelianov
- Email: mark.emelianov@gmail.com
- GitHub: [makoronius](https://github.com/makoronius)

---

**Built with ❤️ using Claude Code**
