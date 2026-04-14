"""
Migration script: Add additional_roles field to all existing users.
Run once to ensure backward compatibility.

Usage:
    cd backend
    python scripts/migrate_additional_roles.py
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db
from datetime import datetime, timezone


async def migrate():
    """Add additional_roles=[] to all users that don't have it."""
    print("Starting migration: add additional_roles to users...")
    
    # Find all users without additional_roles field
    result = db.users.update_many(
        {"additional_roles": {"$exists": False}},
        {"$set": {"additional_roles": [], "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    print(f"Migration complete: {result.modified_count} users updated with additional_roles=[]")
    
    # Verify
    total = await db.users.count_documents({})
    with_field = await db.users.count_documents({"additional_roles": {"$exists": True}})
    print(f"Total users: {total}, with additional_roles field: {with_field}")


if __name__ == "__main__":
    asyncio.run(migrate())
