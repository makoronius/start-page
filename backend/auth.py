#!/usr/bin/env python3

import yaml
import os
from functools import wraps
from flask import session, request, jsonify

USERS_FILE = '/app/users.yaml'

def load_users():
    """Load users and roles from YAML file"""
    try:
        with open(USERS_FILE, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading users: {e}")
        return {'users': [], 'roles': []}

def save_users(data):
    """Save users and roles to YAML file"""
    try:
        with open(USERS_FILE, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        return True
    except Exception as e:
        print(f"Error saving users: {e}")
        return False

def is_local_request():
    """Check if request is from localhost - checks real IP first when behind proxy"""
    local_ips = ['127.0.0.1', 'localhost', '::1']

    # When behind nginx proxy, check X-Real-IP and X-Forwarded-For headers FIRST
    # These contain the actual client IP, not the proxy IP
    real_ip = request.headers.get('X-Real-IP', '').strip()
    forwarded_for = request.headers.get('X-Forwarded-For', '').strip()

    # Check X-Real-IP first (set by nginx)
    if real_ip:
        return real_ip in local_ips

    # Check X-Forwarded-For (first IP in the chain)
    if forwarded_for:
        client_ip = forwarded_for.split(',')[0].strip()
        return client_ip in local_ips

    # Only check remote_addr if no proxy headers (direct connection)
    remote_addr = request.remote_addr
    return remote_addr in local_ips

def get_current_user():
    """Get current logged-in user"""
    if is_local_request():
        # For localhost requests, return admin user
        return {
            'username': 'localhost',
            'roles': ['Admins'],
            'is_local': True,
            'is_admin': True
        }

    if 'username' in session:
        users_data = load_users()
        for user in users_data.get('users', []):
            if user['username'] == session['username']:
                # Check if user has admin privileges
                user_roles = user.get('roles', [])
                is_admin = False
                for role in users_data.get('roles', []):
                    if role['name'] in user_roles:
                        if role.get('is_admin', False) or role['name'] == 'Admins':
                            is_admin = True
                            break

                return {
                    'username': user['username'],
                    'roles': user_roles,
                    'email': user.get('email', ''),
                    'is_local': False,
                    'is_admin': is_admin
                }
    return None

def get_user_categories(user):
    """Get categories accessible by user based on their roles"""
    if not user:
        return []

    users_data = load_users()
    roles = users_data.get('roles', [])

    categories = set()
    for role in roles:
        if role['name'] in user['roles']:
            categories.update(role.get('categories', []))

    return list(categories)

def login_required(f):
    """Decorator to require login for endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Allow local requests without authentication
        if is_local_request():
            return f(*args, **kwargs)

        # Check if user is logged in
        if 'username' not in session:
            return jsonify({"error": "Authentication required", "login_required": True}), 401

        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Allow local requests
        if is_local_request():
            return f(*args, **kwargs)

        user = get_current_user()
        if not user:
            return jsonify({"error": "Admin access required"}), 403

        # Check if user has any role marked as administrator
        users_data = load_users()
        user_roles = user.get('roles', [])

        for role in users_data.get('roles', []):
            if role['name'] in user_roles:
                # Check if role has administrator flag or is the Admins role
                if role.get('is_admin', False) or role['name'] == 'Admins':
                    return f(*args, **kwargs)

        return jsonify({"error": "Admin access required"}), 403

    return decorated_function

def authenticate_user(username, password):
    """Authenticate user with username and password"""
    users_data = load_users()

    for user in users_data.get('users', []):
        if user['username'] == username and user['password'] == password:
            return True

    return False
