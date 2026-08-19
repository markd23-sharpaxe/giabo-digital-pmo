"""Phase 4: the proactive Dynamic Chasing graph -- a lightweight MAF workflow,
separate from `app_graph.py`'s reactive Teams/Outlook triage graph. Turns
`chasing_engine.calculate_chasing_priorities()`'s output into drafted,
highly-contextual Teams check-in messages via `prompts/chasing_agent.md`.

    node_evaluate_priorities -> node_draft_messages

`node_evaluate_priorities` isn't fed by a live Teams/Outlook message the way
`app_graph.py`'s nodes are -- it pulls its own data from `chasing_engine`.
Whatever schedules a run of this graph (see `.cursor/rules/05-maf-cron-governance.mdc`)
may well be periodic, but which tasks actually get chased is entirely
priority-driven: `ChasingWeight.chasing_score`'s 24h fatigue cooldown and
deadline proximity, not a fixed "message everyone" cron sweep (Immutable
Principle 4, "No Cron" -- see `maf_graph_state.ChasingWeight`).
"""

import asyncio
import logging
import os
from pathlib import Path

from agent_framework import Agent, Executor, WorkflowBuilder, WorkflowContext, handler
from pydantic import BaseModel
from typing_extensions import Never

from chasing_engine import calculate_chasing_priorities
from db_middleware import mark_task_contacted

_PROMPT_PATH = Path(__file__).parent / "prompts" / "chasing_agent.md"


class ChasingTick(BaseModel):
    """Trigger message for `node_evaluate_priorities`. Phase 7 (Real Database
    Integration) adds `project_id` -- `chasing_engine.calculate_chasing_priorities`
    now queries the real per-project `tasks` table, so the trigger has to
    say which project this run is for."""

    project_id: str


class PrioritizedTasks(BaseModel):
    project_id: str
    tasks: list[dict]


class DraftedMessage(BaseModel):
    task_id: str
    assignee: str
    task_name: str
    chasing_score: float
    message: str


class DraftedMessages(BaseModel):
    drafts: list[DraftedMessage]


class EvaluatePrioritiesNode(Executor):
    """node_evaluate_priorities: calls `calculate_chasing_priorities()`."""

    def __init__(self, *, id: str = "node_evaluate_priorities") -> None:
        super().__init__(id=id)

    @handler
    async def evaluate(self, message: ChasingTick, ctx: WorkflowContext[PrioritizedTasks]) -> None:
        tasks = calculate_chasing_priorities(message.project_id)
        await ctx.send_message(PrioritizedTasks(project_id=message.project_id, tasks=tasks))


def _render_chasing_prompt(*, task_name: str, assignee: str, days_to_deadline: int, critical_path_impact: int) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return (
        template.replace("{task_name}", task_name)
        .replace("{assignee}", assignee)
        .replace("{days_to_deadline}", str(days_to_deadline))
        .replace("{critical_path_impact}", str(critical_path_impact))
    )


class DraftMessagesNode(Executor):
    """node_draft_messages: for each prioritized task, calls Azure OpenAI with
    `prompts/chasing_agent.md` to draft a contextual Teams check-in message.

    This is a plain (non-structured) call -- the mission is a free-text Teams
    message, not a JSON schema -- so the drafted text comes from
    `AgentResponse.text`, not `.value` (which is only populated when a
    `response_format` was passed to `chat_agent.run`).
    """

    def __init__(self, chat_agent: Agent, *, id: str = "node_draft_messages") -> None:
        super().__init__(id=id)
        self._chat_agent = chat_agent

    @handler
    async def draft(self, message: PrioritizedTasks, ctx: WorkflowContext[Never, DraftedMessages]) -> None:
        drafts: list[DraftedMessage] = []
        for task in message.tasks:
            prompt = _render_chasing_prompt(
                task_name=task["task_name"],
                assignee=task["assignee"],
                days_to_deadline=task["days_to_deadline"],
                critical_path_impact=task["critical_path_impact"],
            )
            response = await self._chat_agent.run(prompt)
            drafts.append(
                DraftedMessage(
                    task_id=task["task_id"],
                    assignee=task["assignee"],
                    task_name=task["task_name"],
                    chasing_score=task["chasing_score"],
                    message=response.text,
                )
            )

            # Phase 7: stamp last_contact_timestamp now that a chase message
            # was actually drafted for this task -- without this, the 24h
            # fatigue cooldown in ChasingWeight.chasing_score would never
            # re-engage, since nothing else ever updates that column. A
            # failed stamp shouldn't discard an otherwise-successful draft,
            # so it's logged rather than raised.
            try:
                mark_task_contacted(task["task_id"], message.project_id)
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to mark task %s as contacted for project %s", task["task_id"], message.project_id
                )

        for draft in drafts:
            print(
                f"--- Draft for {draft.assignee} ({draft.task_id} - {draft.task_name}, "
                f"score={draft.chasing_score:.1f}) ---"
            )
            print(draft.message)
            print()

        await ctx.yield_output(DraftedMessages(drafts=drafts))


def build_chasing_graph(chat_agent: Agent):
    """Wire `node_evaluate_priorities -> node_draft_messages`."""
    evaluate = EvaluatePrioritiesNode()
    draft = DraftMessagesNode(chat_agent)

    builder = WorkflowBuilder(start_executor=evaluate)
    builder.add_edge(evaluate, draft)
    return builder.build()


def build_default_chasing_chat_agent(*, temperature: float = 0.40) -> Agent:
    """Build the Chasing Agent's `Agent` from the `AZURE_OPENAI_*` env vars
    already used elsewhere in this project. Warmer temperature than the
    Change Control Clerk's -- this node drafts conversational check-ins, not
    governance-grade proposals."""
    from agent_framework.openai import OpenAIChatClient

    client = OpenAIChatClient(
        model=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
    )
    return Agent(
        client=client,
        name="GIABOChasingAgent",
        default_options={"temperature": temperature},
    )


async def _main(project_id: str) -> None:
    workflow = build_chasing_graph(build_default_chasing_chat_agent())
    events = await workflow.run(ChasingTick(project_id=project_id))
    outputs = events.get_outputs()
    if not outputs:
        print("No tasks met the Dynamic Chasing threshold this run.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run one Dynamic Chasing tick for a single project.")
    parser.add_argument(
        "--project-id",
        default=os.environ.get("CHASING_PROJECT_ID"),
        help="Project to evaluate (env var CHASING_PROJECT_ID also works). Required.",
    )
    args = parser.parse_args()
    if not args.project_id:
        parser.error("--project-id is required (or set the CHASING_PROJECT_ID env var).")

    asyncio.run(_main(args.project_id))
