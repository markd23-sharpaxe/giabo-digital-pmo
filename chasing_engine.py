"""Phase 4: the Dynamic Chasing Engine (Immutable Principle 4 -- see
`.cursor/rules/08-maf-dynamic-chasing-persona.mdc`). Turns raw task rows into
`ChasingWeight`-scored, fatigue-cooldown-filtered, deadline-sorted priorities.

Phase 7 (Real Database Integration) swaps `get_active_tasks_mock` for the
real `get_active_tasks`, backed by the `tasks` table -- this module's
contract is unchanged: a `list[dict]` of task rows in, a priority-sorted
`list[dict]` out.
"""

from datetime import datetime, timezone

from db_middleware import get_active_tasks
from maf_graph_state import ChasingWeight


def calculate_chasing_priorities(project_id: str) -> list[dict]:
    """
    1. Fetches active tasks for `project_id`.
    2. Calculates datetime math (hours_since_last_contact, days_to_deadline).
    3. Hydrates the ChasingWeight Pydantic model for each.
    4. Filters out tasks with chasing_score == 0.0.
    5. Sorts descending by chasing_score.
    6. Returns the top tasks to chase.
    """
    now = datetime.now(timezone.utc)
    prioritized_tasks: list[dict] = []

    for task in get_active_tasks(project_id):
        last_contact = datetime.fromisoformat(task["last_contact_timestamp"])
        deadline = datetime.fromisoformat(task["deadline"])

        hours_since_last_contact = int((now - last_contact).total_seconds() // 3600)
        days_to_deadline = (deadline - now).days

        weight = ChasingWeight(
            task_id=task["task_id"],
            critical_path_impact=task["critical_path_impact"],
            linked_risks_severity=task["linked_risks_severity"],
            hours_since_last_contact=hours_since_last_contact,
            days_to_deadline=days_to_deadline,
        )

        if weight.chasing_score == 0.0:
            continue  # 24h Fatigue Cooldown -- Immutable Principle 4 (No Cron)

        # The original task row, enriched with its computed priority. ChasingWeight
        # itself doesn't carry task_name/assignee/etc., so downstream consumers
        # (chasing_graph.py's draft node) need both merged into one dict.
        prioritized_tasks.append(
            {
                **task,
                "hours_since_last_contact": hours_since_last_contact,
                "days_to_deadline": days_to_deadline,
                "chasing_score": weight.chasing_score,
            }
        )

    prioritized_tasks.sort(key=lambda t: t["chasing_score"], reverse=True)
    return prioritized_tasks
