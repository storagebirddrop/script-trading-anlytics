#!/usr/bin/env python3
"""
Dashboard Build Script
Generates the dashboard by copying templates and data to the output directory.
"""

import os
import shutil
import json
import sys
from pathlib import Path

DASHBOARD_JSON_PATH = 'data/dashboard.json'
DASHBOARD_OUTPUT_DIR = 'dashboard'
TEMPLATES_DIR = 'dashboard/templates'
ASSETS_OUTPUT_DIR = 'dashboard/assets'


def main():
    """Main execution function."""
    print("=" * 60)
    print("Dashboard Build Script")
    print("=" * 60)
    print()
    
    # Check if dashboard.json exists
    if not os.path.exists(DASHBOARD_JSON_PATH):
        print(f"ERROR: {DASHBOARD_JSON_PATH} not found")
        print("Please run calculate_metrics.py first to generate dashboard.json")
        sys.exit(1)
    
    # Create output directories
    print("Creating output directories...")
    os.makedirs(ASSETS_OUTPUT_DIR, exist_ok=True)
    print(f"✓ Created {ASSETS_OUTPUT_DIR}")
    print()
    
    # Copy dashboard.json to assets directory
    print("Copying dashboard data...")
    shutil.copy2(DASHBOARD_JSON_PATH, os.path.join(ASSETS_OUTPUT_DIR, 'data.json'))
    print(f"✓ Copied {DASHBOARD_JSON_PATH} to {ASSETS_OUTPUT_DIR}/data.json")
    print()
    
    # Copy HTML template to output directory
    print("Copying HTML template...")
    template_path = os.path.join(TEMPLATES_DIR, 'index.html')
    output_path = os.path.join(DASHBOARD_OUTPUT_DIR, 'index.html')
    
    if os.path.exists(template_path):
        shutil.copy2(template_path, output_path)
        print(f"✓ Copied {template_path} to {output_path}")
    else:
        print(f"ERROR: Template not found at {template_path}")
        sys.exit(1)
    print()
    
    # Verify CSS and JS are in place
    print("Verifying CSS and JS files...")
    css_path = os.path.join(DASHBOARD_OUTPUT_DIR, 'css', 'styles.css')
    js_path = os.path.join(DASHBOARD_OUTPUT_DIR, 'js', 'dashboard.js')
    
    if os.path.exists(css_path):
        print(f"✓ CSS file exists: {css_path}")
    else:
        print(f"ERROR: CSS file not found: {css_path}")
        sys.exit(1)
    
    if os.path.exists(js_path):
        print(f"✓ JS file exists: {js_path}")
    else:
        print(f"ERROR: JS file not found: {js_path}")
        sys.exit(1)
    print()
    
    # Validate dashboard.json structure
    print("Validating dashboard.json structure...")
    try:
        with open(DASHBOARD_JSON_PATH, 'r') as f:
            dashboard_data = json.load(f)
        
        if 'metadata' not in dashboard_data:
            print("ERROR: dashboard.json missing 'metadata' section")
            sys.exit(1)
        
        if 'assets' not in dashboard_data:
            print("ERROR: dashboard.json missing 'assets' section")
            sys.exit(1)
        
        print(f"✓ Valid dashboard.json with {len(dashboard_data['assets'])} assets")
        print(f"✓ Last updated: {dashboard_data['metadata'].get('last_updated', 'Unknown')}")
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in dashboard.json: {e}")
        sys.exit(1)
    print()
    
    # Print summary
    print("=" * 60)
    print("Dashboard build completed successfully")
    print("=" * 60)
    print(f"Output directory: {DASHBOARD_OUTPUT_DIR}")
    print(f"Files generated:")
    print(f"  - {DASHBOARD_OUTPUT_DIR}/index.html")
    print(f"  - {ASSETS_OUTPUT_DIR}/data.json")
    print(f"  - {DASHBOARD_OUTPUT_DIR}/css/styles.css")
    print(f"  - {DASHBOARD_OUTPUT_DIR}/js/dashboard.js")
    print()
    print("To view the dashboard locally, open:")
    print(f"  file://{os.path.abspath(output_path)}")
    print()


if __name__ == "__main__":
    main()
