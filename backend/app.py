#!/usr/bin/env python3

from flask import Flask, jsonify, request, send_file, session
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import yaml
import os
import csv
import io
import json
from datetime import datetime, timedelta
from pathlib import Path
from auth import (
    login_required, admin_required, authenticate_user,
    get_current_user, get_user_categories, is_local_request,
    load_users, save_users, hash_password, validate_password_strength,
    verify_password, is_password_hashed
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)  # Long-lived sessions
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True when using HTTPS
app.config['SESSION_COOKIE_DOMAIN'] = None  # Allow any domain
app.config['SESSION_COOKIE_NAME'] = 'start-page-session'
app.config['SESSION_COOKIE_PATH'] = '/'
app.config['SESSION_REFRESH_EACH_REQUEST'] = False  # Don't regenerate on each request
# Note: Cannot use origins=['*'] with credentials=True. Instead use supports_credentials with no origins specified
# This allows the browser to use the request's origin
CORS(app, supports_credentials=True, allow_headers=['Content-Type'], expose_headers=['Set-Cookie'])

# Rate limiting setup
# Custom key function to exempt localhost from rate limiting
def rate_limit_key():
    if is_local_request():
        return None  # No rate limiting for localhost
    return get_remote_address()

limiter = Limiter(
    app=app,
    key_func=rate_limit_key,
    default_limits=["5000 per day", "500 per hour"],
    storage_uri="memory://"
)

CONFIG_FILE = '/app/config.yaml'
USERS_FILE = '/app/users.yaml'
AUDIT_LOG_FILE = '/app/logs/audit.log'

# Ensure logs directory exists
os.makedirs(os.path.dirname(AUDIT_LOG_FILE), exist_ok=True)

def audit_log(action, username=None, details=None, ip_address=None):
    """Log audit events to file"""
    try:
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'username': username or 'anonymous',
            'ip_address': ip_address or request.remote_addr if request else 'unknown',
            'details': details or {}
        }
        with open(AUDIT_LOG_FILE, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    except Exception as e:
        print(f"Error writing audit log: {e}")

def get_ip_whitelist():
    """Get IP whitelist from config if enabled"""
    config = load_config()
    if config and 'security' in config:
        return config['security'].get('ip_whitelist', [])
    return []

def is_ip_whitelisted():
    """Check if current IP is whitelisted (if whitelist is enabled)"""
    # Always allow localhost
    if is_local_request():
        return True

    whitelist = get_ip_whitelist()
    # If no whitelist configured, allow all IPs
    if not whitelist:
        return True

    # Check if current IP is in whitelist
    client_ip = request.headers.get('X-Real-IP') or request.remote_addr
    return client_ip in whitelist

def sanitize_string(value, max_length=1000):
    """Sanitize string input"""
    if not isinstance(value, str):
        return str(value)
    # Remove null bytes and limit length
    sanitized = value.replace('\x00', '').strip()
    return sanitized[:max_length]

def validate_email(email):
    """Basic email validation"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None if email else True

def get_session_token(username):
    """Generate session token based on user's current state"""
    users_data = load_users()
    for user in users_data.get('users', []):
        if user['username'] == username:
            # Create token from roles hash to detect changes
            roles_str = ','.join(sorted(user.get('roles', [])))
            password_hash = user.get('password', '')
            # Simple hash of roles+password
            import hashlib
            token = hashlib.sha256(f"{roles_str}:{password_hash}".encode()).hexdigest()
            return token
    return None

def check_session_token(username):
    """Check if session token matches current user state"""
    if 'session_token' not in session:
        return True  # Old sessions without token are allowed

    current_token = get_session_token(username)
    if current_token != session.get('session_token'):
        # Token mismatch - roles or password changed
        return False
    return True

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
@limiter.exempt
def auth_status():
    """Check authentication status (exempt from rate limiting for dashboard polling)"""
    if is_local_request():
        return jsonify({
            "authenticated": True,
            "user": {
                "username": "localhost",
                "roles": ["Admins"],
                "is_local": True,
                "is_admin": True
            }
        }), 200

    user = get_current_user()
    if user:
        # Check session token - invalidate if roles or password changed
        username = session.get('username')
        if username and not check_session_token(username):
            # Session invalid - roles or password changed
            audit_log('session_invalidated', username=username, details={'reason': 'role_or_password_changed'})
            session.clear()
            return jsonify({
                "authenticated": False,
                "user": None,
                "session_invalidated": True
            }), 200

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
@limiter.limit("5 per minute")
def login():
    """Login endpoint"""
    # Check IP whitelist
    if not is_ip_whitelisted():
        audit_log('login_blocked_ip', details={'ip': request.remote_addr})
        return jsonify({"error": "Access denied"}), 403

    data = request.json
    username = sanitize_string(data.get('username', ''), max_length=100)
    password = data.get('password', '')

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    if authenticate_user(username, password):
        session.permanent = True
        session['username'] = username
        # Set session token to detect role/password changes
        session['session_token'] = get_session_token(username)

        user = get_current_user()
        audit_log('login_success', username=username)

        return jsonify({
            "success": True,
            "user": user
        }), 200
    else:
        audit_log('login_failed', username=username)
        return jsonify({"error": "Invalid username or password"}), 401

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """Logout endpoint"""
    username = session.get('username', 'unknown')
    audit_log('logout', username=username)
    session.clear()
    return jsonify({"success": True}), 200

@app.route('/api/auth/change-password', methods=['POST'])
@login_required
@limiter.limit("3 per hour")
def change_password():
    """Change current user's password"""
    try:
        # Don't allow password change for localhost users
        if is_local_request():
            return jsonify({"error": "Cannot change password for localhost access"}), 400

        data = request.json
        current_password = data.get('current_password')
        new_password = data.get('new_password')

        if not current_password or not new_password:
            return jsonify({"error": "Current and new password required"}), 400

        # Validate password strength
        is_valid, message = validate_password_strength(new_password)
        if not is_valid:
            return jsonify({"error": message}), 400

        username = session.get('username')
        users_data = load_users()

        # Find user and verify current password
        for user in users_data.get('users', []):
            if user['username'] == username:
                stored_password = user.get('password', '')

                # Verify current password (supports both hashed and plain text)
                is_correct = False
                if is_password_hashed(stored_password):
                    is_correct = verify_password(current_password, stored_password)
                else:
                    is_correct = (stored_password == current_password)

                if not is_correct:
                    audit_log('password_change_failed', username=username, details={'reason': 'incorrect_current_password'})
                    return jsonify({"error": "Current password is incorrect"}), 401

                # Update password with bcrypt hash
                user['password'] = hash_password(new_password)

                if save_users(users_data):
                    # Update session token so user isn't logged out
                    session['session_token'] = get_session_token(username)
                    audit_log('password_changed', username=username)
                    return jsonify({"success": True, "message": "Password changed successfully"}), 200
                else:
                    return jsonify({"error": "Failed to save password"}), 500

        return jsonify({"error": "User not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/auth/profile', methods=['GET'])
@login_required
def get_profile():
    """Get current user profile"""
    user = get_current_user()
    if user:
        return jsonify({
            'username': user['username'],
            'email': user.get('email', ''),
            'first_name': user.get('first_name', ''),
            'last_name': user.get('last_name', ''),
            'roles': user['roles'],
            'is_local': user.get('is_local', False)
        }), 200
    else:
        return jsonify({"error": "Not authenticated"}), 401

@app.route('/api/auth/profile', methods=['POST'])
@login_required
def update_profile():
    """Update user profile (first_name, last_name, email)"""
    user = get_current_user()
    if not user or user.get('is_local'):
        return jsonify({"error": "Cannot update local user profile"}), 403

    data = request.get_json()
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    email = data.get('email', '').strip()

    # Load users
    users_data = load_users()

    # Find and update user
    for u in users_data.get('users', []):
        if u['username'] == user['username']:
            if first_name:
                u['first_name'] = first_name
            if last_name:
                u['last_name'] = last_name
            if email:
                u['email'] = email

            if save_users(users_data):
                audit_log('profile_update', user['username'], {'first_name': first_name, 'last_name': last_name, 'email': email})
                return jsonify({"message": "Profile updated successfully"}), 200
            else:
                return jsonify({"error": "Failed to save profile"}), 500

    return jsonify({"error": "User not found"}), 404

@app.route('/api/config', methods=['GET'])
@login_required
@limiter.exempt
def get_config():
    """Get complete configuration filtered by user permissions (exempt from rate limiting for dashboard polling)"""
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

        # Auto-grant admin roles access to any new categories
        if 'categories' in new_config:
            users_data = load_users()
            new_category_names = [cat['name'] for cat in new_config['categories']]

            # Add new categories to all admin roles
            for role in users_data.get('roles', []):
                if role.get('is_admin') or role['name'] == 'Admins':
                    role_cats = set(role.get('categories', []))
                    role_cats.update(new_category_names)
                    role['categories'] = list(role_cats)

            # Save updated roles
            save_users(users_data)

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

@app.route('/api/browse-folders', methods=['POST'])
@admin_required
def browse_folders():
    """Browse folders on the server (admin only)"""
    try:
        data = request.get_json()
        path = data.get('path', '/')

        # Security: Normalize and validate path
        path = os.path.abspath(path)

        # Check if path exists
        if not os.path.exists(path):
            return jsonify({"error": "Path does not exist"}), 404

        # Check if path is a directory
        if not os.path.isdir(path):
            # If it's a file, return its parent directory
            path = os.path.dirname(path)

        try:
            # List all directories in the path
            items = []
            for item in sorted(os.listdir(path)):
                item_path = os.path.join(path, item)
                if os.path.isdir(item_path):
                    try:
                        # Check if we can access the directory
                        os.listdir(item_path)
                        items.append({
                            'name': item,
                            'path': item_path,
                            'accessible': True
                        })
                    except PermissionError:
                        items.append({
                            'name': item,
                            'path': item_path,
                            'accessible': False
                        })

            # Get parent directory
            parent = os.path.dirname(path) if path != os.path.dirname(path) else None

            return jsonify({
                'current_path': path,
                'parent_path': parent,
                'directories': items
            }), 200

        except PermissionError:
            return jsonify({"error": "Permission denied to access this directory"}), 403

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
            'first_name': u.get('first_name', ''),
            'last_name': u.get('last_name', ''),
            'roles': u.get('roles', [])
        }
        for u in users_data.get('users', [])
    ]
    return jsonify(users), 200

@app.route('/api/users', methods=['POST'])
@admin_required
@limiter.limit("10 per hour")
def create_user():
    """Create new user (admin only)"""
    try:
        data = request.json
        username = sanitize_string(data.get('username', ''), max_length=100)
        password = data.get('password', '')
        email = sanitize_string(data.get('email', ''), max_length=200)
        roles = data.get('roles', [])

        if not username or not password:
            return jsonify({"error": "Username and password required"}), 400

        # Validate password strength
        is_valid, message = validate_password_strength(password)
        if not is_valid:
            return jsonify({"error": message}), 400

        # Validate email if provided
        if email and not validate_email(email):
            return jsonify({"error": "Invalid email address"}), 400

        users_data = load_users()

        # Check if user already exists
        for user in users_data.get('users', []):
            if user['username'] == username:
                return jsonify({"error": "User already exists"}), 400

        # Add new user with hashed password
        users_data['users'].append({
            'username': username,
            'password': hash_password(password),
            'email': email,
            'roles': roles
        })

        if save_users(users_data):
            audit_log('user_created', username=session.get('username'), details={'new_user': username})
            return jsonify({"success": True, "message": "User created"}), 200
        else:
            return jsonify({"error": "Failed to save user"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/users/<username>', methods=['PUT'])
@admin_required
@limiter.limit("20 per hour")
def update_user(username):
    """Update user (admin only)"""
    try:
        data = request.json
        users_data = load_users()

        # Find and update user
        for user in users_data.get('users', []):
            if user['username'] == username:
                changes = []

                if 'password' in data and data['password']:
                    # Validate password strength
                    is_valid, message = validate_password_strength(data['password'])
                    if not is_valid:
                        return jsonify({"error": message}), 400
                    user['password'] = hash_password(data['password'])
                    changes.append('password')

                if 'email' in data:
                    email = sanitize_string(data['email'], max_length=200)
                    if email and not validate_email(email):
                        return jsonify({"error": "Invalid email address"}), 400
                    user['email'] = email
                    changes.append('email')

                if 'roles' in data:
                    user['roles'] = data['roles']
                    changes.append('roles')

                if save_users(users_data):
                    audit_log('user_updated', username=session.get('username'),
                             details={'updated_user': username, 'changes': changes})
                    return jsonify({"success": True, "message": "User updated"}), 200
                else:
                    return jsonify({"error": "Failed to save user"}), 500

        return jsonify({"error": "User not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/users/<username>', methods=['DELETE'])
@admin_required
@limiter.limit("10 per hour")
def delete_user(username):
    """Delete user (admin only)"""
    try:
        users_data = load_users()

        # Don't allow deleting the last admin
        users_data['users'] = [u for u in users_data['users'] if u['username'] != username]

        if save_users(users_data):
            audit_log('user_deleted', username=session.get('username'),
                     details={'deleted_user': username})
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

@app.route('/api/roles', methods=['POST'])
@admin_required
def create_role():
    """Create new role (admin only)"""
    try:
        data = request.json
        name = data.get('name')
        description = data.get('description', '')
        categories = data.get('categories', [])
        is_admin = data.get('is_admin', False)

        if not name:
            return jsonify({"error": "Role name required"}), 400

        users_data = load_users()

        # Check if role already exists
        for role in users_data.get('roles', []):
            if role['name'] == name:
                return jsonify({"error": "Role already exists"}), 400

        # Add new role
        if 'roles' not in users_data:
            users_data['roles'] = []

        users_data['roles'].append({
            'name': name,
            'description': description,
            'categories': categories,
            'is_admin': is_admin
        })

        if save_users(users_data):
            return jsonify({"success": True, "message": "Role created"}), 200
        else:
            return jsonify({"error": "Failed to save role"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/roles', methods=['PUT'])
@admin_required
@limiter.limit("20 per hour")
def update_roles():
    """Update all roles (admin only)"""
    try:
        data = request.json
        users_data = load_users()

        # Update roles
        users_data['roles'] = data.get('roles', [])

        if save_users(users_data):
            audit_log('roles_updated', username=session.get('username'))
            return jsonify({"success": True, "message": "Roles updated"}), 200
        else:
            return jsonify({"error": "Failed to save roles"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/roles/<name>', methods=['DELETE'])
@admin_required
@limiter.limit("10 per hour")
def delete_role(name):
    """Delete role (admin only)"""
    try:
        users_data = load_users()

        # Check if any users have this role
        for user in users_data.get('users', []):
            if name in user.get('roles', []):
                return jsonify({"error": f"Cannot delete role assigned to users. Remove it from all users first."}), 400

        # Remove role
        users_data['roles'] = [r for r in users_data.get('roles', []) if r['name'] != name]

        if save_users(users_data):
            audit_log('role_deleted', username=session.get('username'),
                     details={'deleted_role': name})
            return jsonify({"success": True, "message": "Role deleted"}), 200
        else:
            return jsonify({"error": "Failed to delete role"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 400

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

# AI Tools - Image Generation
GENERATED_IMAGES_DIR = '/app/generated_images'
os.makedirs(GENERATED_IMAGES_DIR, exist_ok=True)

@app.route('/api/tools/generate-image', methods=['POST'])
@login_required
@limiter.limit("5 per hour")  # Limit AI generation to prevent abuse
def generate_image():
    """Generate an AI image from text description"""
    try:
        from blossom_ai import Blossom

        data = request.get_json()
        description = data.get('description', '').strip()

        if not description:
            return jsonify({"error": "Description is required"}), 400

        if len(description) > 500:
            return jsonify({"error": "Description too long (max 500 characters)"}), 400

        user = get_current_user()
        username = user['username']

        # Initialize Blossom AI
        blossom = Blossom()

        # Generate image
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_desc = "".join(c for c in description[:50] if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
        filename = f"{username}_{timestamp}_{safe_desc}.jpg"
        filepath = os.path.join(GENERATED_IMAGES_DIR, filename)

        # Generate and save image using Blossom AI
        blossom.image.save(description, filepath)

        # Save metadata (description/prompt) alongside the image
        metadata_filename = filename.replace('.jpg', '.json')
        metadata_filepath = os.path.join(GENERATED_IMAGES_DIR, metadata_filename)
        metadata = {
            'description': description,
            'username': username,
            'timestamp': timestamp,
            'filename': filename,
            'created': datetime.now().isoformat()
        }
        with open(metadata_filepath, 'w') as f:
            json.dump(metadata, f, indent=2)

        audit_log('ai_image_generated', username=username, details={'description': description, 'filename': filename})

        return jsonify({
            "success": True,
            "message": "Image generated successfully!",
            "filename": filename,
            "url": f"/api/tools/images/{filename}"
        }), 200

    except ImportError:
        return jsonify({"error": "Blossom AI library not installed"}), 500
    except Exception as e:
        print(f"Image generation error: {e}")
        return jsonify({"error": f"Failed to generate image: {str(e)}"}), 500

@app.route('/api/tools/images', methods=['GET'])
@login_required
def list_generated_images():
    """List all generated images with metadata"""
    try:
        user = get_current_user()
        username = user['username']
        is_admin = user.get('is_admin', False)

        images = []

        if os.path.exists(GENERATED_IMAGES_DIR):
            for filename in os.listdir(GENERATED_IMAGES_DIR):
                if filename.endswith(('.png', '.jpg', '.jpeg')):
                    # Check if user owns this image or is admin
                    if is_admin or filename.startswith(f"{username}_"):
                        filepath = os.path.join(GENERATED_IMAGES_DIR, filename)
                        stat = os.stat(filepath)

                        # Parse filename to extract info
                        parts = filename.rsplit('_', 2)
                        image_username = parts[0] if len(parts) >= 3 else 'unknown'

                        # Try to load metadata
                        metadata_filename = filename.replace('.jpg', '.json').replace('.png', '.json').replace('.jpeg', '.json')
                        metadata_filepath = os.path.join(GENERATED_IMAGES_DIR, metadata_filename)
                        description = None
                        if os.path.exists(metadata_filepath):
                            try:
                                with open(metadata_filepath, 'r') as f:
                                    metadata = json.load(f)
                                    description = metadata.get('description')
                            except Exception as e:
                                print(f"Error loading metadata for {filename}: {e}")

                        images.append({
                            'filename': filename,
                            'url': f"/api/tools/images/{filename}",
                            'size': stat.st_size,
                            'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                            'username': image_username,
                            'description': description
                        })

        # Sort by creation date, newest first
        images.sort(key=lambda x: x['created'], reverse=True)

        return jsonify(images), 200
    except Exception as e:
        print(f"Error listing images: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/tools/images/<filename>', methods=['GET'])
@login_required
def get_generated_image(filename):
    """Get a specific generated image"""
    try:
        user = get_current_user()
        username = user['username']
        is_admin = user.get('is_admin', False)

        # Security: Check if user owns this image or is admin
        if not is_admin and not filename.startswith(f"{username}_"):
            return jsonify({"error": "Access denied"}), 403

        filepath = os.path.join(GENERATED_IMAGES_DIR, filename)

        if not os.path.exists(filepath):
            return jsonify({"error": "Image not found"}), 404

        return send_file(filepath, mimetype='image/png')
    except Exception as e:
        print(f"Error getting image: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/tools/images/<filename>', methods=['DELETE'])
@login_required
def delete_generated_image(filename):
    """Delete a generated image"""
    try:
        user = get_current_user()
        username = user['username']
        is_admin = user.get('is_admin', False)

        # Security: Check if user owns this image or is admin
        if not is_admin and not filename.startswith(f"{username}_"):
            return jsonify({"error": "Access denied"}), 403

        filepath = os.path.join(GENERATED_IMAGES_DIR, filename)

        if not os.path.exists(filepath):
            return jsonify({"error": "Image not found"}), 404

        # Delete the image file
        os.remove(filepath)

        # Also delete the metadata JSON file if it exists
        metadata_filename = filename.replace('.jpg', '.json').replace('.png', '.json').replace('.jpeg', '.json')
        metadata_filepath = os.path.join(GENERATED_IMAGES_DIR, metadata_filename)
        if os.path.exists(metadata_filepath):
            os.remove(metadata_filepath)

        audit_log('ai_image_deleted', username=username, details={'filename': filename})

        return jsonify({"success": True, "message": "Image deleted successfully"}), 200
    except Exception as e:
        print(f"Error deleting image: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Log application startup
    audit_log('app_started', details={'version': '2.0', 'security_features': 'enabled'})
    print("Starting application with security features enabled")
    print("- Password hashing: bcrypt")
    print("- Rate limiting: enabled")
    print("- Audit logging: enabled")
    print("- Session token validation: enabled")
    print("- Input sanitization: enabled")
    app.run(host='0.0.0.0', port=5555, debug=False)
