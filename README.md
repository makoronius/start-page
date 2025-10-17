# Start Page - Local Services Dashboard

A beautiful, feature-rich dashboard for managing and accessing your local development services with role-based access control, customizable themes, and immersive ambient sounds.

![Dashboard Preview](docs/screenshot.png)

## ✨ Features

### 🎨 Visual & UX
- **Multi-Theme Support**: Light, Dark, and System themes with 4 color schemes (Default, Vibrant, Pastel, Monochrome)
- **Dynamic Backgrounds**: Time-of-day and seasonal particle animations
- **Ambient Sounds**: Realistic soundscapes (Rain, Ocean, Forest Birds, Coffee Shop, Fireplace)
- **Responsive Design**: Works seamlessly on desktop, tablet, and mobile
- **Customizable Grid**: Choose between 1-4 columns or auto-layout

### 🔐 Security & Access Control
- **User Authentication**: Secure login with bcrypt password hashing
- **Role-Based Access**: Fine-grained permissions per category
- **Admin Panel**: Complete user and role management
- **Localhost Bypass**: Automatic admin access from localhost
- **Session Management**: Long-lived, secure sessions
- **Audit Logging**: Track all administrative actions

### 📊 Service Management
- **Category Organization**: Group services into custom categories
- **Drag & Drop**: Reorder services and categories
- **Status Indicators**: Visual service health status
- **Favorites**: Star services for quick access
- **Search & Filter**: Find services quickly
- **Quick Links**: One-click access to all services

### ⚙️ Configuration
- **Web-Based Config**: No file editing required
- **Systems Management**: Organize categories and services
- **CSV Export**: Generate port mapping files
- **Backup/Restore**: Configuration backup system
- **Live Reload**: Changes apply immediately

### 🎵 Customization
- **Ambient Sounds**: 5 realistic soundscapes with volume control
- **Particle Effects**: Automatic or manual time/season selection
- **Sound Effects**: Interactive UI feedback sounds
- **Emoji Icons**: Beautiful service icons with emoji picker
- **Flexible Layout**: Customize columns and grid appearance

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose
- (Optional) Python 3.11+ for local development

### Installation

1. **Clone the repository**:
   ```bash
   git clone <your-repo-url> /opt/start-page
   cd /opt/start-page
   ```

2. **Create configuration files**:
   ```bash
   cp config.yaml.example config.yaml
   cp users.yaml.example users.yaml
   ```

3. **Edit configuration**:
   - Edit `config.yaml` with your services
   - Edit `users.yaml` to set passwords (they'll be auto-hashed on first use)

4. **Deploy with Docker**:
   ```bash
   docker compose up -d
   ```

5. **Access the dashboard**:
   - Open `http://localhost` in your browser
   - Login with credentials from `users.yaml`
   - From localhost, you have automatic admin access

## 📁 Project Structure

```
start-page/
├── public/
│   └── index.html              # Single-page application
├── backend/
│   ├── app.py                  # Flask API server
│   ├── auth.py                 # Authentication & authorization
│   └── requirements.txt        # Python dependencies
├── scripts/
│   └── Update-DockerPortProxy.ps1  # Windows port proxy management
├── config.yaml.example         # Sample configuration
├── users.yaml.example          # Sample users & roles
├── docker-compose.yml          # Docker deployment config
├── Dockerfile                  # Container image definition
└── README.md                   # This file
```

## ⚙️ Configuration

### config.yaml

The main configuration file defines settings, categories, and services:

```yaml
settings:
  hostname: localhost
  title: "Local Services Dashboard"
  subtitle: "Your development environment at a glance"
  auto_refresh_minutes: 5
  grid_columns: auto  # auto, 1, 2, 3, or 4

categories:
  - name: "Development"
    icon: "💻"
    description: "Development tools"

services:
  - name: "Portainer"
    icon: "🐳"
    url: "http://localhost:9000"
    description: "Docker management"
    port: 9000
    local: true
    status: running
    category: "Development"
```

See `config.yaml.example` for a complete example.

### users.yaml

Defines users, roles, and permissions:

```yaml
users:
  - username: "admin"
    password: "changeme"  # Auto-hashed on first use
    email: "admin@example.com"
    first_name: "Admin"
    last_name: "User"
    roles:
      - "Admins"

roles:
  - name: "Admins"
    description: "Full system access"
    is_admin: true
    categories:
      - "Development"
      - "Monitoring"
```

See `users.yaml.example` for a complete example.

## 🔐 Authentication & Authorization

### User Roles

- **Admins**: Full access to all categories and configuration
- **Custom Roles**: Define roles with specific category access
- **Localhost**: Automatic admin access when browsing from localhost

### Password Security

- Passwords are automatically hashed with bcrypt on first login
- Plain text passwords are migrated to hashed versions automatically
- Password strength requirements enforced for new passwords

### Access Control

Users can only see services in categories assigned to their roles. Admins can:
- Manage all users
- Create and edit roles
- Configure categories and services
- Access all system features

## 🎨 Customization Features

### Themes

**Color Themes**:
- **Default**: Purple gradient
- **Vibrant**: Pink gradient
- **Pastel**: Soft colors
- **Monochrome**: Grayscale

**Mode**: Light, Dark, or System

### Particle Animations

**Time of Day** (affects intensity and count):
- **Morning**: Golden particles, 45 count, 1.2x intensity
- **Afternoon**: Sky blue, 40 count, 1.0x intensity
- **Evening**: Sunset colors, 50 count, 1.3x intensity
- **Night**: Deep purple, 60 count, 1.5x intensity

**Season** (affects visual style):
- **Summer**: Sun splashes with wave animation
- **Autumn**: Falling leaves
- **Winter**: Gentle snowfall
- **Spring**: Floating sparkles

Both can be set to **Automatic** or manual selection.

### Ambient Sounds

**Available Soundscapes**:
- **Gentle Rain**: Soothing rainfall
- **Ocean Waves**: Beach atmosphere
- **Forest Birds**: Realistic chirping with intervals
- **Coffee Shop**: Layered café ambience with steam and clinks
- **Fireplace**: Warm crackling fire

**Features**:
- Volume control slider
- Auto-starts on page load
- Persists across sessions

## 🐳 Docker Deployment

### docker-compose.yml

```yaml
services:
  start-page:
    build: .
    ports:
      - "80:80"
    volumes:
      - ./config.yaml:/app/config.yaml
      - ./users.yaml:/app/users.yaml
      - ./logs:/app/logs
    restart: unless-stopped
```

### Environment Variables

- `SECRET_KEY`: Flask session secret (auto-generated if not set)

### Volumes

- `config.yaml`: Service configuration (persisted)
- `users.yaml`: User accounts and roles (persisted)
- `logs/`: Audit logs (persisted)

## 🔧 Development

### Local Development (without Docker)

1. **Install Python dependencies**:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. **Run the Flask backend**:
   ```bash
   python app.py
   ```

3. **Serve the frontend**:
   ```bash
   cd public
   python -m http.server 8000
   ```

4. **Access**:
   - Frontend: `http://localhost:8000`
   - API: `http://localhost:5555`

### API Endpoints

**Authentication**:
- `POST /api/auth/login` - User login
- `POST /api/auth/logout` - User logout
- `GET /api/auth/me` - Current user info
- `GET /api/auth/profile` - User profile
- `POST /api/auth/profile` - Update profile
- `POST /api/auth/change-password` - Change password

**Configuration**:
- `GET /api/config` - Get configuration
- `POST /api/config` - Update configuration
- `GET /api/csv` - Generate CSV export

**Admin**:
- `GET /api/users` - List all users
- `POST /api/users` - Create user
- `PUT /api/users/<username>` - Update user
- `DELETE /api/users/<username>` - Delete user

## 🎯 Usage Tips

### Adding Services

1. Navigate to **Config > Systems**
2. Add a category (if needed)
3. Click **+ Add New Service** under a category
4. Fill in details and save

### Managing Users

1. Navigate to **Config > Users & Access**
2. Create users and assign roles
3. Define role permissions by category access

### Favorites

Click the ⭐ icon on any service card to add it to favorites. Access favorites from the dedicated tab.

### Customization

Go to **Settings > Customization**:
- Toggle sound effects
- Choose ambient background sound
- Adjust volume
- Select particle animation mode
- Pick your theme

## 🛠️ Troubleshooting

### Cannot Login

- Check `users.yaml` exists and contains valid users
- Verify password (will be hashed on first login)
- Check browser console for errors

### Services Not Loading

- Verify `config.yaml` is valid YAML
- Check Docker container logs: `docker logs start-page`
- Ensure config file is mounted correctly

### Port Conflicts

```bash
# Check if port 80 is in use
netstat -an | grep :80

# Or change port in docker-compose.yml:
ports:
  - "8080:80"  # Use port 8080 instead
```

### Theme Not Persisting

- Ensure cookies are enabled
- Check browser localStorage is accessible
- Try clearing browser cache

## 📊 Port Proxy Scripts (Windows + WSL2)

### Setup

1. Copy scripts to `C:\Scripts\`:
   ```powershell
   Copy-Item scripts\*.ps1 C:\Scripts\
   Copy-Item scripts\*.csv C:\Scripts\
   ```

2. Run as Administrator:
   ```powershell
   cd C:\Scripts
   .\Update-DockerPortProxy.ps1
   ```

### Features

- Automatic WSL2 IP detection
- Firewall rule creation
- Port proxy management
- CSV-based configuration

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📝 License

MIT License - see LICENSE file for details

## 👤 Author

**Mark Emelianov**
- Email: mark.emelianov@gmail.com
- GitHub: [@makoronius](https://github.com/makoronius)

---

**Built with ❤️ using Claude Code**
