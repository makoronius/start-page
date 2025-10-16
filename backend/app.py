#!/usr/bin/env python3

from flask import Flask, jsonify, request, send_file, session
from flask_cors import CORS
import yaml
import os
import csv
import io
from datetime import timedelta
from auth import (
    login_required, admin_required, authenticate_user,
    get_current_user, get_user_categories, is_local_request,
    load_users, save_users
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)  # Infinite sessions
CORS(app, supports_credentials=True)

CONFIG_FILE = '/app/config.yaml'
USERS_FILE = '/app/users.yaml'

def load_config():
    """Load configuration from YAML file"""
    try:
        with open(CONFIG_FILE, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        return None

def save_config(config):
    """Save configuration to YAML file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200

# Authentication endpoints
@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    """Check authentication status"""
    if is_local_request():
        return jsonify({
            "authenticated": True,
            "user": {
                "username": "localhost",
                "roles": ["Admins"],
                "is_local": True
            }
        }), 200

    user = get_current_user()
    if user:
        return jsonify({
            "authenticated": True,
            "user": user
        }), 200
    else:
        return jsonify({
            "authenticated": False,
            "user": None
        }), 200

@app.route('/api/auth/login', methods=['POST'])
def login():
    """Login endpoint"""
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    if authenticate_user(username, password):
        session.permanent = True
        session['username'] = username
        user = get_current_user()
        return jsonify({
            "success": True,
            "user": user
        }), 200
    else:
        return jsonify({"error": "Invalid username or password"}), 401

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """Logout endpoint"""
    session.clear()
    return jsonify({"success": True}), 200

@app.route('/api/config', methods=['GET'])
@login_required
def get_config():
    """Get complete configuration filtered by user permissions"""
    config = load_config()
    if not config:
        return jsonify({"error": "Failed to load configuration"}), 500

    user = get_current_user()
    user_categories = get_user_categories(user)

    # Filter services by user categories
    if 'services' in config:
        filtered_services = [
            s for s in config['services']
            if s.get('category') in user_categories
        ]
        config['services'] = filtered_services

    # Filter categories by user access
    if 'categories' in config:
        filtered_categories = [
            c for c in config['categories']
            if c['name'] in user_categories
        ]
        config['categories'] = filtered_categories

    return jsonify(config), 200

@app.route('/api/config', methods=['POST'])
@admin_required
def update_config():
    """Update complete configuration (admin only)"""
    try:
        new_config = request.json
        if save_config(new_config):
            return jsonify({"success": True, "message": "Configuration updated"}), 200
        else:
            return jsonify({"error": "Failed to save configuration"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/services', methods=['GET'])
@login_required
def get_services():
    """Get services list filtered by user permissions"""
    config = load_config()
    if not config or 'services' not in config:
        return jsonify({"error": "Failed to load services"}), 500

    user = get_current_user()
    user_categories = get_user_categories(user)

    # Filter services by user categories
    filtered_services = [
        s for s in config['services']
        if s.get('category') in user_categories
    ]

    return jsonify(filtered_services), 200

@app.route('/api/services', methods=['POST'])
@admin_required
def update_services():
    """Update services list (admin only)"""
    try:
        config = load_config()
        if not config:
            return jsonify({"error": "Failed to load configuration"}), 500

        config['services'] = request.json
        if save_config(config):
            return jsonify({"success": True, "message": "Services updated"}), 200
        else:
            return jsonify({"error": "Failed to save configuration"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/csv/generate', methods=['POST'])
@admin_required
def generate_csv_to_server():
    """Generate CSV file and save to configured path on server"""
    try:
        config = load_config()
        if not config or 'port_mappings' not in config:
            return jsonify({"error": "No port mappings found in configuration"}), 404

        # Get settings
        settings = config.get('settings', {})
        csv_path = settings.get('csv_path', '/scripts/port-mappings.csv')
        backup_path = settings.get('backup_path', '/scripts/backups')

        # Create backup directory if it doesn't exist
        os.makedirs(backup_path, exist_ok=True)

        # Create backup of existing file if it exists
        if os.path.exists(csv_path):
            from datetime import datetime
            backup_filename = f"port-mappings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            backup_full_path = os.path.join(backup_path, backup_filename)
            try:
                import shutil
                shutil.copy2(csv_path, backup_full_path)
                backup_created = True
            except Exception as e:
                print(f"Warning: Could not create backup: {e}")
                backup_created = False
        else:
            backup_created = False

        # Generate CSV content
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(['Port', 'Service', 'Description'])

        # Write port mappings
        for mapping in config['port_mappings']:
            writer.writerow([
                mapping.get('port', ''),
                mapping.get('service', ''),
                mapping.get('description', '')
            ])

        # Write to file
        csv_dir = os.path.dirname(csv_path)
        os.makedirs(csv_dir, exist_ok=True)

        with open(csv_path, 'w', newline='') as f:
            f.write(output.getvalue())

        return jsonify({
            "success": True,
            "message": f"CSV generated successfully at {csv_path}",
            "backup_created": backup_created,
            "csv_path": csv_path
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/csv/download', methods=['GET'])
def download_csv():
    """Download CSV file from port mappings in config"""
    try:
        config = load_config()
        if not config or 'port_mappings' not in config:
            return jsonify({"error": "No port mappings found in configuration"}), 404

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(['Port', 'Service', 'Description'])

        # Write port mappings
        for mapping in config['port_mappings']:
            writer.writerow([
                mapping.get('port', ''),
                mapping.get('service', ''),
                mapping.get('description', '')
            ])

        # Convert to bytes
        output.seek(0)
        csv_bytes = io.BytesIO(output.getvalue().encode('utf-8'))

        return send_file(
            csv_bytes,
            mimetype='text/csv',
            as_attachment=True,
            download_name='port-mappings.csv'
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/csv/content', methods=['GET'])
def get_csv_content():
    """Get CSV content as text"""
    try:
        config = load_config()
        if not config or 'port_mappings' not in config:
            return jsonify({"error": "No port mappings found in configuration"}), 404

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(['Port', 'Service', 'Description'])

        # Write port mappings
        for mapping in config['port_mappings']:
            writer.writerow([
                mapping.get('port', ''),
                mapping.get('service', ''),
                mapping.get('description', '')
            ])

        return jsonify({"csv": output.getvalue()}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/settings', methods=['GET'])
@login_required
def get_settings():
    """Get general settings"""
    config = load_config()
    if config and 'settings' in config:
        return jsonify(config['settings']), 200
    else:
        return jsonify({"error": "Failed to load settings"}), 500

@app.route('/api/settings', methods=['POST'])
@admin_required
def update_settings():
    """Update general settings (admin only)"""
    try:
        config = load_config()
        if not config:
            return jsonify({"error": "Failed to load configuration"}), 500

        config['settings'] = request.json
        if save_config(config):
            return jsonify({"success": True, "message": "Settings updated"}), 200
        else:
            return jsonify({"error": "Failed to save configuration"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# User management endpoints
@app.route('/api/users', methods=['GET'])
@admin_required
def get_users():
    """Get all users (admin only)"""
    users_data = load_users()
    # Don't send passwords to frontend
    users = [
        {
            'username': u['username'],
            'email': u.get('email', ''),
            'roles': u.get('roles', [])
        }
        for u in users_data.get('users', [])
    ]
    return jsonify(users), 200

@app.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    """Create new user (admin only)"""
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        email = data.get('email', '')
        roles = data.get('roles', [])

        if not username or not password:
            return jsonify({"error": "Username and password required"}), 400

        users_data = load_users()

        # Check if user already exists
        for user in users_data.get('users', []):
            if user['username'] == username:
                return jsonify({"error": "User already exists"}), 400

        # Add new user
        users_data['users'].append({
            'username': username,
            'password': password,
            'email': email,
            'roles': roles
        })

        if save_users(users_data):
            return jsonify({"success": True, "message": "User created"}), 200
        else:
            return jsonify({"error": "Failed to save user"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/users/<username>', methods=['PUT'])
@admin_required
def update_user(username):
    """Update user (admin only)"""
    try:
        data = request.json
        users_data = load_users()

        # Find and update user
        for user in users_data.get('users', []):
            if user['username'] == username:
                if 'password' in data and data['password']:
                    user['password'] = data['password']
                if 'email' in data:
                    user['email'] = data['email']
                if 'roles' in data:
                    user['roles'] = data['roles']

                if save_users(users_data):
                    return jsonify({"success": True, "message": "User updated"}), 200
                else:
                    return jsonify({"error": "Failed to save user"}), 500

        return jsonify({"error": "User not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/users/<username>', methods=['DELETE'])
@admin_required
def delete_user(username):
    """Delete user (admin only)"""
    try:
        users_data = load_users()

        # Don't allow deleting the last admin
        users_data['users'] = [u for u in users_data['users'] if u['username'] != username]

        if save_users(users_data):
            return jsonify({"success": True, "message": "User deleted"}), 200
        else:
            return jsonify({"error": "Failed to delete user"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# Role management endpoints
@app.route('/api/roles', methods=['GET'])
@admin_required
def get_roles():
    """Get all roles (admin only)"""
    users_data = load_users()
    return jsonify(users_data.get('roles', [])), 200

@app.route('/api/categories', methods=['GET'])
@login_required
def get_categories():
    """Get categories accessible by user"""
    config = load_config()
    if not config or 'categories' not in config:
        return jsonify([]), 200

    user = get_current_user()
    user_categories = get_user_categories(user)

    # Filter categories by user access
    filtered_categories = [
        c for c in config['categories']
        if c['name'] in user_categories
    ]

    return jsonify(filtered_categories), 200

@app.route('/api/categories', methods=['POST'])
@admin_required
def create_category():
    """Create new category (admin only)"""
    try:
        data = request.json
        config = load_config()

        if 'categories' not in config:
            config['categories'] = []

        config['categories'].append(data)

        if save_config(config):
            return jsonify({"success": True, "message": "Category created"}), 200
        else:
            return jsonify({"error": "Failed to save category"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/categories/<name>', methods=['DELETE'])
@admin_required
def delete_category(name):
    """Delete category if empty (admin only)"""
    try:
        config = load_config()

        # Check if category has services
        has_services = any(s.get('category') == name for s in config.get('services', []))

        if has_services:
            return jsonify({"error": "Cannot delete category with services"}), 400

        config['categories'] = [c for c in config.get('categories', []) if c['name'] != name]

        if save_config(config):
            return jsonify({"success": True, "message": "Category deleted"}), 200
        else:
            return jsonify({"error": "Failed to delete category"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5555, debug=True)
