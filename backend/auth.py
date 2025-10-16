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
    """Check if request is from localhost"""
    remote_addr = request.remote_addr
    forwarded_for = request.headers.get('X-Forwarded-For', '')
    real_ip = request.headers.get('X-Real-IP', '')

    # Check if request is from localhost
    local_ips = ['127.0.0.1', 'localhost', '::1']

    if remote_addr in local_ips:
        return True
    if forwarded_for and forwarded_for.split(',')[0].strip() in local_ips:
        return True
    if real_ip in local_ips:
        return True

    return False

def get_current_user():
    """Get current logged-in user"""
    if is_local_request():
        # For localhost requests, return admin user
        return {
            'username': 'localhost',
            'roles': ['Admins'],
            'is_local': True
        }

    if 'username' in session:
        users_data = load_users()
        for user in users_data.get('users', []):
            if user['username'] == session['username']:
                return {
                    'username': user['username'],
                    'roles': user.get('roles', []),
                    'email': user.get('email', ''),
                    'is_local': False
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
        if not user or 'Admins' not in user['roles']:
            return jsonify({"error": "Admin access required"}), 403

        return f(*args, **kwargs)
    return decorated_function

def authenticate_user(username, password):
    """Authenticate user with username and password"""
    users_data = load_users()

    for user in users_data.get('users', []):
        if user['username'] == username and user['password'] == password:
            return True

    return False
