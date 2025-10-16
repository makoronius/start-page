#!/usr/bin/env python3

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import yaml
import os
import csv
import io

app = Flask(__name__)
CORS(app)

CONFIG_FILE = '/app/config.yaml'

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

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get complete configuration"""
    config = load_config()
    if config:
        return jsonify(config), 200
    else:
        return jsonify({"error": "Failed to load configuration"}), 500

@app.route('/api/config', methods=['POST'])
def update_config():
    """Update complete configuration"""
    try:
        new_config = request.json
        if save_config(new_config):
            return jsonify({"success": True, "message": "Configuration updated"}), 200
        else:
            return jsonify({"error": "Failed to save configuration"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/services', methods=['GET'])
def get_services():
    """Get services list"""
    config = load_config()
    if config and 'services' in config:
        return jsonify(config['services']), 200
    else:
        return jsonify({"error": "Failed to load services"}), 500

@app.route('/api/services', methods=['POST'])
def update_services():
    """Update services list"""
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
def get_settings():
    """Get general settings"""
    config = load_config()
    if config and 'settings' in config:
        return jsonify(config['settings']), 200
    else:
        return jsonify({"error": "Failed to load settings"}), 500

@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Update general settings"""
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5555, debug=True)
