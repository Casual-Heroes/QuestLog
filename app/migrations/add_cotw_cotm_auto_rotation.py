"""
Migration: Add Auto-Rotation for COTW/COTM
Created: 2025-01-XX
Description: Adds auto_rotate and rotation_day fields to DiscoveryConfig
             for automatic Creator of the Week/Month rotation
"""

from alembic import op
import sqlalchemy as sa


def upgrade():
    """Add COTW/COTM auto-rotation fields."""

    # Add COTW auto-rotation fields
    op.add_column('discovery_configs',
        sa.Column('cotw_auto_rotate', sa.Boolean(), default=False, server_default='0'))
    op.add_column('discovery_configs',
        sa.Column('cotw_rotation_day', sa.Integer(), default=1, server_default='1'))

    # Add COTM auto-rotation fields
    op.add_column('discovery_configs',
        sa.Column('cotm_auto_rotate', sa.Boolean(), default=False, server_default='0'))
    op.add_column('discovery_configs',
        sa.Column('cotm_rotation_day', sa.Integer(), default=1, server_default='1'))

    print("✅ COTW/COTM auto-rotation fields added successfully")


def downgrade():
    """Remove COTW/COTM auto-rotation fields."""

    op.drop_column('discovery_configs', 'cotm_rotation_day')
    op.drop_column('discovery_configs', 'cotm_auto_rotate')
    op.drop_column('discovery_configs', 'cotw_rotation_day')
    op.drop_column('discovery_configs', 'cotw_auto_rotate')

    print("✅ COTW/COTM auto-rotation fields removed")
