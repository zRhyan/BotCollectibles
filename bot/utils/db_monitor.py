from sqlalchemy import text
from database.session import get_session

async def check_sequence_gaps():
    """
    Utility function to check for gaps in card IDs
    """
    async with get_session() as session:
        # Get gaps
        result = await session.execute(
            text("""
                SELECT t1.id + 1 AS gap_start,
                       (SELECT MIN(t3.id) - 1
                        FROM cards t3
                        WHERE t3.id > t1.id) AS gap_end
                FROM cards t1
                WHERE NOT EXISTS (SELECT t2.id
                                FROM cards t2
                                WHERE t2.id = t1.id + 1)
                  AND EXISTS (SELECT t3.id
                            FROM cards t3
                            WHERE t3.id > t1.id)
                ORDER BY t1.id;
            """)
        )
        gaps = result.fetchall()
        
        # Get sequence info
        seq_info = await session.execute(
            text("SELECT last_value, is_called FROM cards_id_seq;")
        )
        seq_data = seq_info.fetchone()
        
        return {
            "gaps": gaps,
            "sequence_last_value": seq_data[0] if seq_data else None,
            "sequence_is_called": seq_data[1] if seq_data else None
        }
