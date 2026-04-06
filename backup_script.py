"""
Backup Script for FEA Contour Plot Project
Creates zip backup of project files (excluding .venv, output, __pycache__)
Saves backup to backup/ folder
"""

import zipfile
import os
import glob
from datetime import datetime

# Configuration
EXCLUDE_DIRS = ['.venv', 'output', '__pycache__', 'input', 'backup']
EXCLUDE_EXTENSIONS = ['.zip', '.log', '.pyc']
BACKUP_FOLDER = 'backup'

def create_backup():
    """Create backup zip file"""
    # Create backup folder if not exists
    os.makedirs(BACKUP_FOLDER, exist_ok=True)
    
    # Generate backup filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f"backup_{timestamp}.zip"
    backup_path = os.path.join(BACKUP_FOLDER, backup_filename)
    
    print(f"Creating backup: {backup_path}")
    
    # Get list of files to backup
    files_to_backup = []
    for root, dirs, files in os.walk('.'):
        # Remove excluded directories from search
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        # Add files (excluding certain extensions)
        for file in files:
            if not any(file.endswith(ext) for ext in EXCLUDE_EXTENSIONS):
                filepath = os.path.join(root, file)
                files_to_backup.append(filepath)
    
    print(f"Found {len(files_to_backup)} files to backup")
    
    # Create zip file
    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for filepath in files_to_backup:
            # Get relative path for archive
            arcname = os.path.relpath(filepath, '.')
            zipf.write(filepath, arcname)
            print(f"  + {arcname}")
    
    # Get file size
    file_size = os.path.getsize(backup_path)
    file_size_mb = file_size / (1024 * 1024)
    
    print(f"\n✓ Backup created successfully!")
    print(f"  File: {backup_filename}")
    print(f"  Size: {file_size_mb:.2f} MB")
    print(f"  Files: {len(files_to_backup)}")
    
    return backup_path


def list_backups():
    """List all backup files"""
    backups = glob.glob(os.path.join(BACKUP_FOLDER, 'backup_*.zip'))
    
    if not backups:
        print("No backups found.")
        return
    
    print(f"\nAvailable backups ({len(backups)}):")
    print("-" * 60)
    
    for backup in sorted(backups):
        filename = os.path.basename(backup)
        size = os.path.getsize(backup)
        size_mb = size / (1024 * 1024)
        mtime = datetime.fromtimestamp(os.path.getmtime(backup))
        
        print(f"  {filename:<35} {size_mb:>8.2f} MB  {mtime.strftime('%Y-%m-%d %H:%M')}")


def restore_backup(backup_filename=None):
    """Restore from backup file"""
    if backup_filename is None:
        # Get latest backup
        backups = glob.glob(os.path.join(BACKUP_FOLDER, 'backup_*.zip'))
        if not backups:
            print("No backups found.")
            return
        backup_filename = sorted(backups)[-1]
        print(f"Using latest backup: {backup_filename}")
    
    if not os.path.exists(backup_filename):
        print(f"Backup file not found: {backup_filename}")
        return
    
    print(f"Restoring from: {backup_filename}")
    
    with zipfile.ZipFile(backup_filename, 'r') as zipf:
        zipf.extractall('.')
        files = zipf.namelist()
    
    print(f"✓ Restored {len(files)} files")
    
    return files


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == '--list':
            list_backups()
        elif sys.argv[1] == '--restore':
            backup_file = sys.argv[2] if len(sys.argv) > 2 else None
            restore_backup(backup_file)
        elif sys.argv[1] == '--help':
            print("""
Backup Script for FEA Contour Plot Project

Usage:
    python backup_script.py              Create new backup
    python backup_script.py --list       List all backups
    python backup_script.py --restore    Restore latest backup
    python backup_script.py --restore <filename>  Restore specific backup
    python backup_script.py --help       Show this help
""")
        else:
            print(f"Unknown option: {sys.argv[1]}")
            print("Use --help for usage information")
    else:
        create_backup()
