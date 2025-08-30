#!/usr/bin/env python3
"""
Configuration setup utility for Workshop Inventory Tracking
"""

import os
import shutil
from config import Config

def setup_environment():
    """Interactive setup for environment configuration"""
    
    print("Workshop Inventory Tracking - Configuration Setup")
    print("=" * 50)
    
    # Check if .env file exists
    env_file = '.env'
    if not os.path.exists(env_file):
        print(f"\nCreating {env_file} from template...")
        if os.path.exists('.env.example'):
            shutil.copy('.env.example', env_file)
            print(f"✓ Created {env_file} from .env.example")
        else:
            create_env_file(env_file)
    else:
        print(f"\n✓ {env_file} already exists")
    
    # Validate configuration
    print("\nValidating configuration...")
    config_errors = Config.validate_config()
    
    if config_errors:
        print("\n❌ Configuration Issues Found:")
        for error in config_errors:
            print(f"  - {error}")
        print("\nNext steps:")
        if not Config.GOOGLE_SHEET_ID:
            print("  1. Set GOOGLE_SHEET_ID in your .env file")
        if not os.path.exists(Config.GOOGLE_CREDENTIALS_FILE):
            print("  2. Download credentials.json from Google Cloud Console")
            print("     and place it in the project root directory")
    else:
        print("✓ Configuration looks good!")
    
    print(f"\nConfiguration files expected:")
    print(f"  - Credentials: {Config.GOOGLE_CREDENTIALS_FILE}")
    print(f"  - Token file: {Config.GOOGLE_TOKEN_FILE} (auto-generated)")
    print(f"  - Environment: {env_file}")

def create_env_file(filepath):
    """Create a basic .env file"""
    content = """# Flask Configuration
SECRET_KEY=your-secret-key-here
FLASK_DEBUG=True

# Google Sheets API Configuration
GOOGLE_CREDENTIALS_FILE=credentials.json
GOOGLE_TOKEN_FILE=token.json
GOOGLE_SHEET_ID=your-google-sheet-id-here

# Application Configuration  
LOG_LEVEL=INFO
"""
    with open(filepath, 'w') as f:
        f.write(content)
    print(f"✓ Created basic {filepath}")

def main():
    """Main setup function"""
    try:
        setup_environment()
    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())