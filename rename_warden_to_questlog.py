"""
Rename Warden → QuestLog in the ch-webserver website
Preserves database names and infrastructure
"""
import os
import re
from pathlib import Path

# Replacements to make
REPLACEMENTS = [
    # Display names
    ('Warden Bot', 'QuestLog'),
    ('WardenBot', 'QuestLog'),
    ('warden_bot', 'questlog'),

    # URLs and routes - be careful!
    ('/warden/', '/questlog/'),
    ('warden-dashboard', 'questlog-dashboard'),
    ('wardenbot', 'questlog'),

    # Text references
    ('the Warden bot', 'QuestLog'),
    ('The Warden bot', 'QuestLog'),
    ('Warden features', 'QuestLog features'),
]

# DO NOT replace these
PROTECTED_STRINGS = [
    'warden_',  # Table names
    'DB_NAME=warden',
    'DB_USER=warden',
    "database': 'warden'",
    'warden.db',
    'from warden',  # Python imports if any
]

def is_protected_line(line):
    """Check if line should be protected"""
    for protected in PROTECTED_STRINGS:
        if protected in line:
            return True
    return False

def replace_in_file(filepath):
    """Replace Warden with QuestLog"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        original_content = content
        lines = content.split('\n')
        new_lines = []

        for line in lines:
            if is_protected_line(line):
                new_lines.append(line)
                continue

            new_line = line
            for old, new in REPLACEMENTS:
                new_line = new_line.replace(old, new)

            new_lines.append(new_line)

        new_content = '\n'.join(new_lines)

        if new_content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return True

        return False

    except Exception as e:
        print(f"Error: {filepath}: {e}")
        return False

def main():
    base_path = Path('/srv/ch-webserver/app')

    # File extensions to process
    extensions = ['.py', '.html', '.js']

    files_to_process = []
    for ext in extensions:
        files_to_process.extend(base_path.rglob(f'*{ext}'))

    print(f"Found {len(files_to_process)} files to process")

    changed_files = []
    for filepath in files_to_process:
        if replace_in_file(filepath):
            changed_files.append(filepath)
            print(f"✓ {filepath.relative_to(base_path.parent)}")

    print(f"\n✅ Updated {len(changed_files)} files")

if __name__ == "__main__":
    main()
