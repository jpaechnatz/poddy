"""add episode_title_exclude_strings to feed

Revision ID: 00ba830c76e4
Revises: c3d8e1f0a271
Create Date: 2026-11-17 14:47:27.743111

"""

# revision identifiers, used by Alembic.
revision = "00ba830c76e4"
down_revision = "c3d8e1f0a271"
branch_labels = None
depends_on = None

# Poddy: the fork already adds feed.episode_title_exclude_strings in its own
# revision 22ee5a64f8c1, which every database at head has run. Upstream's
# add_column here would fail with "duplicate column name" (and on a fresh
# database the two branches may run in either order), so this revision only
# keeps upstream's history intact and changes nothing. The column belongs to
# 22ee5a64f8c1, which also drops it on downgrade.


def upgrade():
    pass


def downgrade():
    pass
