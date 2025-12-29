"""
Migration: Add Custom Admin Roles
Created: 2025-12-29
Description: Adds admin_roles field to guilds table for hybrid permission system
             (Discord permissions + custom role-based admin access)
"""

from alembic import op
import sqlalchemy as sa


def upgrade():
    """Add admin_roles field to guilds table."""

    # Add admin_roles column (JSON array of Discord role IDs)
    op.add_column('guilds',
        sa.Column('admin_roles', sa.Text(), nullable=True))

    print("✅ admin_roles field added to guilds table successfully")
    print("   Guilds can now configure custom admin roles for dashboard access")


def downgrade():
    """Remove admin_roles field from guilds table."""

    op.drop_column('guilds', 'admin_roles')

    print("✅ admin_roles field removed from guilds table")
