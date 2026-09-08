"""
DEPRECATED - replaced by database/graph_db.py.

This module held the correlation graph in two Python lists pre-loaded with
invented suspects. Real correlations were lost on every restart while the
fictional ones came back, which meant fabricated links could be presented as
findings.

Importing it now raises rather than silently reviving that behaviour.
"""

raise ImportError(
    "database.neo4j_db has been replaced by database.graph_db. "
    "Use `from database.graph_db import graph_manager`."
)
