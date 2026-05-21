"""Named constants for cycle-related activity-log ``action`` strings.

Phase 1G: keeps the wording consistent across endpoints so the
frontend activity-log renderer can string-match on stable values and
attach icons / colors per event type. Prior to this module each
endpoint emitted its own free-text phrase ("Cycle Started", "Cycle
Closed", "PO appended to cycle") — easy for drift to creep in.

Constants are the *display* strings, not opaque codes — the activity
log row stores them verbatim and surfaces them in the timeline UI.
Using a constant import at the call site is the single source of
truth; anyone who wants to add a new cycle event adds the constant
here first.
"""

# Lifecycle transitions on the cycle envelope itself.
CYCLE_STARTED = "Cycle Started"
CYCLE_CLOSED = "Cycle Closed"
CYCLE_ABANDONED = "Cycle Abandoned"

# Operational events that mutate the cycle's contents.
PO_APPENDED_TO_CYCLE = "PO appended to cycle"
LOI_APPENDED_TO_CYCLE = "LOI appended to cycle"

# Export / report generation events. Logged so admins can see who
# pulled the cycle's Excel and when (useful for audit during renewal
# conversations with the customer).
CYCLE_EXPORTED_XLSX = "Cycle exported to Excel"


__all__ = [
    "CYCLE_STARTED",
    "CYCLE_CLOSED",
    "CYCLE_ABANDONED",
    "PO_APPENDED_TO_CYCLE",
    "LOI_APPENDED_TO_CYCLE",
    "CYCLE_EXPORTED_XLSX",
]
