#!/usr/bin/env python3
"""
Import IGDB keywords from txt file into database.

Usage:
    python scripts/import_igdb_keywords.py
    python scripts/import_igdb_keywords.py --file /path/to/igdb_keywords.txt
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from .env if it exists
from dotenv import load_dotenv
load_dotenv()

from app.db import get_db_session
from sqlalchemy import text

DEFAULT_FILE = os.path.join(os.path.dirname(__file__), '..', 'igdb_keywords.txt')


def import_keywords(filepath: str):
    """Import keywords from file.

    Supports two formats:
    1. Tab-separated: id\\tname
    2. Space-aligned (from fetch_igdb_keywords.py output): '   12345  keyword name'
    """

    # Resolve to absolute path if relative
    if not os.path.isabs(filepath):
        filepath = os.path.abspath(filepath)

    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        return False

    # Read and parse the file
    keywords = []
    import re
    # Pattern for space-aligned format: leading spaces, digits, 2+ spaces, then name
    space_pattern = re.compile(r'^\s*(\d+)\s{2,}(.+)$')

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n\r')
            if not line.strip():
                continue

            keyword_id = None
            name = None

            # Try tab-separated format first
            if '\t' in line:
                parts = line.split('\t', 1)
                if len(parts) == 2:
                    try:
                        keyword_id = int(parts[0].strip())
                        name = parts[1].strip()
                    except ValueError:
                        pass
            else:
                # Try space-aligned format (from fetch_igdb_keywords.py output)
                match = space_pattern.match(line)
                if match:
                    try:
                        keyword_id = int(match.group(1))
                        name = match.group(2).strip()
                    except ValueError:
                        pass

            if keyword_id and name:
                # Generate slug from name
                slug = name.lower().replace(' ', '-').replace("'", '')
                keywords.append((keyword_id, name, slug))

    if not keywords:
        print("No keywords found in file")
        return False

    print(f"Found {len(keywords)} keywords to import")

    with get_db_session() as db:
        # Clear existing keywords
        db.execute(text("DELETE FROM igdb_keywords"))
        print("Cleared existing keywords")

        # Batch insert
        batch_size = 500
        for i in range(0, len(keywords), batch_size):
            batch = keywords[i:i + batch_size]
            values = ", ".join([
                f"({kw[0]}, '{kw[1].replace(chr(39), chr(39)+chr(39))}', '{kw[2]}')"
                for kw in batch
            ])
            db.execute(
                text(f"INSERT INTO igdb_keywords (id, name, slug) VALUES {values}")
            )
            print(f"  Inserted {min(i + batch_size, len(keywords))} / {len(keywords)}")

        db.commit()
        print(f"\nSuccessfully imported {len(keywords)} keywords")
        return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Import IGDB keywords to database')
    parser.add_argument('--file', '-f', type=str, default=DEFAULT_FILE,
                        help=f'Path to keywords file (default: {DEFAULT_FILE})')
    args = parser.parse_args()

    success = import_keywords(args.file)
    sys.exit(0 if success else 1)
