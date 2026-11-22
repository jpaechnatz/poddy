"""merge upstream call_type with fork migrations

Revision ID: b0387578cbcd
Revises: 9dff1f50ee31, c3d8e1f0a271
Create Date: 2026-11-22 19:20:19.024074

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "b0387578cbcd"
down_revision = ("9dff1f50ee31", "c3d8e1f0a271")
branch_labels = None
depends_on = None

# Poddy's AI summaries (podcast_processor/episode_extras.py) use the sentinel
# segment ranges -300 (final summary) and -301, -302, ... (parts). Upstream's
# c3d8e1f0a271 left them as "classification"; label them so they keep their
# own rows next to the new call types.
_SUMMARY_ROWS = (
    "language IS NULL "
    "AND first_segment_sequence_num <= -300 "
    "AND last_segment_sequence_num = first_segment_sequence_num"
)


def upgrade():
    op.execute(
        f"UPDATE model_call SET call_type = 'summary' "
        f"WHERE call_type = 'classification' AND {_SUMMARY_ROWS}"
    )


def downgrade():
    op.execute(
        f"UPDATE model_call SET call_type = 'classification' "
        f"WHERE call_type = 'summary' AND {_SUMMARY_ROWS}"
    )
