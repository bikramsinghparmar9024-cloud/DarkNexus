"""
DEPRECATED - this script fabricated evidence and must not be run.

It inserted eight invented intelligence records, four invented surveillance
targets, three invented crypto wallets, and a graph of fictional suspects
directly into the operational database. Those records were indistinguishable
from collected evidence once stored: they appeared in record counts, threat
alerts, hotspot analysis, correlation output and dossier exports.

Several of the .onion addresses it inserted contained a literal "..." and could
never resolve, so they were not merely unverified - they were impossible.

For a system of record intended to support prosecution, writing fabricated
material into the evidence store is the most damaging thing this codebase did.
The admin investigator account, which was the only legitimate thing seeded
here, is created at application startup instead (see app.seed_initial_data).

To remove records this script previously inserted:

    python scripts/purge_demo_data.py            # report only
    python scripts/purge_demo_data.py --apply    # delete them
"""

raise ImportError(
    "database.seed_data has been removed: it wrote fabricated evidence into "
    "the operational database. The admin account is seeded at application "
    "startup. To clean up records it previously inserted, run "
    "scripts/purge_demo_data.py."
)
