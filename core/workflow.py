"""PMO Commander Router Node and MAF directed graph (01-maf-core-orchestrator.mdc).

Migrates the custom Replit 2-stage GIABO pipeline onto a Microsoft Agent
Framework (MAF) directed graph:

    SharePoint delta -> SwarmState -> PMO Commander Router Node
        -> (structured JSON routing decision, DELTA_DISPATCH_EXCLUDED_AGENTS
            stripped) -> parallel fan-out to the selected Specialist Agent
            Nodes (MAF multi-selection edge group == the rule's "conditional
            Edges"), all executed within one BSP superstep ("Parallel
            Execution").

Specialist agent business logic (RAID writebacks, readonly analysis, LLM
prompts, DB writes) lives in each agent's own module; this file only builds
and dispatches the graph shape. Pass real implementations in via
`build_pmo_workflow(..., specialist_runners={...})`.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Awaitable, Callable, Optional, Sequence

from agent_framework import Agent, Executor, WorkflowBuilder, WorkflowContext, handler
from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import Never

from core.billing import AGENT_REGISTRY, AgentTier
from core.state import DELTA_DISPATCH_EXCLUDED_AGENTS, AgentExecutionOutput, SwarmState

logger = logging.getLogger(__name__)

# The full delta-dispatch candidate roster: every non-cron agent in the
# registry. Cron/governance sweeps (05-maf-cron-governance.mdc) are never
# wired into this graph at all -- `filter_excluded_agents` below is a second,
# defensive layer enforcing the same rule at runtime.
DELTA_DISPATCH_CANDIDATE_AGENTS: tuple[str, ...] = tuple(
    sorted(key for key, spec in AGENT_REGISTRY.items() if spec.agent_tier is not AgentTier.CRON)
)


def filter_excluded_agents(roster: Sequence[str]) -> list[str]:
    """Strip DELTA_DISPATCH_EXCLUDED_AGENTS from `roster`.

    Per 01-maf-core-orchestrator.mdc: "The Router Node must NEVER see
    DELTA_DISPATCH_EXCLUDED_AGENTS ... Strip these from the roster before
    injecting into the state." Call this BEFORE constructing a `SwarmState`
    or a routing prompt -- never after.
    """
    return [agent_key for agent_key in roster if agent_key not in DELTA_DISPATCH_EXCLUDED_AGENTS]


class RouterDecision(BaseModel):
    """Structured JSON output contract for the PMO Commander Router Node."""

    model_config = ConfigDict(extra="forbid")

    selected_agent_keys: list[str] = Field(
        default_factory=list, description="Subset of the active roster relevant to this delta."
    )
    rationale: str = Field(description="One or two sentences explaining the routing decision.")


class RoutedDispatch(BaseModel):
    """Message sent from the Router Node into the fan-out edge group."""

    state: SwarmState
    decision: RouterDecision


_ROUTER_SYSTEM_PROMPT = """You are the PMO Commander, the routing brain of a \
Digital PMO agent swarm. You receive one SharePoint delta and a roster of \
available specialist agents, each with a declared RAID/reporting scope. \
Decide exactly which agents in the roster are relevant to this delta and \
must be dispatched in parallel. Never invent an agent key that is not in \
the roster you were given. If nothing in the roster is relevant, return an \
empty `selected_agent_keys` list."""


class PMOCommanderRouter(Executor):
    """The Router Node (01-maf-core-orchestrator.mdc).

    Evaluates `SwarmState.delta_payload` against `SwarmState.active_agent_roster`
    using an LLM constrained to `RouterDecision`'s JSON schema (structured
    output), then forwards a `RoutedDispatch` for the fan-out edge group to
    act on.
    """

    def __init__(self, chat_agent: Agent, *, id: str = "pmo_commander_router") -> None:
        super().__init__(id=id)
        self._chat_agent = chat_agent

    @handler
    async def route(self, state: SwarmState, ctx: WorkflowContext[RoutedDispatch]) -> None:
        # Defense in depth: never let excluded agents reach the prompt, even
        # if they somehow ended up on the incoming roster.
        roster = filter_excluded_agents(state.active_agent_roster)

        if not roster:
            empty_decision = RouterDecision(selected_agent_keys=[], rationale="Active roster was empty after filtering.")
            await ctx.send_message(RoutedDispatch(state=state, decision=empty_decision))
            return

        prompt = self._build_prompt(state, roster)
        response = await self._chat_agent.run(prompt, options={"response_format": RouterDecision})
        decision = response.value or RouterDecision(
            selected_agent_keys=[], rationale="Router returned no structured output; failing safe to no dispatch."
        )

        # Never trust the model to introduce an agent outside the filtered
        # roster (prompt-injection / hallucination guard).
        safe_selection = [key for key in decision.selected_agent_keys if key in roster]
        if len(safe_selection) != len(decision.selected_agent_keys):
            dropped = sorted(set(decision.selected_agent_keys) - set(safe_selection))
            logger.warning("PMOCommanderRouter dropped out-of-roster agent keys: %s", dropped)
        decision = decision.model_copy(update={"selected_agent_keys": safe_selection})

        routed_state = state.model_copy(update={"active_agent_roster": roster})
        await ctx.send_message(RoutedDispatch(state=routed_state, decision=decision))

    @staticmethod
    def _build_prompt(state: SwarmState, roster: list[str]) -> str:
        roster_scope = {key: list(AGENT_REGISTRY[key].scope) for key in roster if key in AGENT_REGISTRY}
        payload = {
            "project_id": str(state.project_id),
            "delta": state.delta_payload.model_dump(mode="json"),
            "available_agents": roster_scope,
        }
        return f"{_ROUTER_SYSTEM_PROMPT}\n\nDelta and roster:\n{json.dumps(payload, indent=2)}"


SpecialistRunner = Callable[[SwarmState, RouterDecision], Awaitable[Optional[dict[str, Any]]]]


class SpecialistAgentExecutor(Executor):
    """Generic dispatch target for one specialist agent node.

    Wraps the agent's own execution callable (its real prompt/tooling/DB
    writeback logic lives in that agent's module -- out of scope here). This
    class exists purely to give every roster entry a graph node that MAF can
    fan out to in parallel.
    """

    def __init__(self, agent_key: str, run_specialist: Optional[SpecialistRunner] = None, *, id: Optional[str] = None) -> None:
        super().__init__(id=id or agent_key)
        self.agent_key = agent_key
        self._run_specialist = run_specialist

    @handler
    async def dispatch(self, message: RoutedDispatch, ctx: WorkflowContext[Never, AgentExecutionOutput]) -> None:
        try:
            if self._run_specialist is not None:
                result = await self._run_specialist(message.state, message.decision)
            else:
                # Graph-only stub: no real implementation wired in yet.
                result = {"scope": list(AGENT_REGISTRY[self.agent_key].scope)}
            output = AgentExecutionOutput(agent_key=self.agent_key, status="success", output=result or {})
        except Exception as exc:  # noqa: BLE001 - surfaced as a failed output, not a graph crash
            output = AgentExecutionOutput(agent_key=self.agent_key, status="failed", error_message=str(exc))

        await ctx.yield_output(output)


def select_by_router_decision(message: RoutedDispatch, available_executor_ids: list[str]) -> list[str]:
    """`add_multi_selection_edge_group` selection function.

    Fans the routed dispatch out only to the executors whose id (== agent_key)
    the Router selected. This IS the "conditional Edges" from
    01-maf-core-orchestrator.mdc, and MAF runs every selected target
    concurrently within one BSP superstep ("Parallel Execution").
    """
    selected = set(message.decision.selected_agent_keys)
    return [executor_id for executor_id in available_executor_ids if executor_id in selected]


def build_pmo_workflow(
    chat_agent: Agent,
    *,
    specialist_runners: Optional[dict[str, SpecialistRunner]] = None,
    agent_keys: Sequence[str] = DELTA_DISPATCH_CANDIDATE_AGENTS,
):
    """Construct the PMO delta-dispatch directed graph.

    Router -> (structured JSON decision) -> multi-selection fan-out ->
    the selected Specialist Agent Nodes, executed in parallel.

    Args:
        chat_agent: An `Agent` (e.g. built by `build_default_chat_agent`)
            used by the Router for structured-output routing decisions.
        specialist_runners: Optional map of agent_key -> async callable
            `(state, decision) -> dict | None` implementing that agent's real
            logic. Agents without an entry get a graph-only stub executor.
        agent_keys: The delta-dispatch candidate roster to wire into the
            graph. Defaults to every non-cron agent in `AGENT_REGISTRY`.
    """
    excluded = DELTA_DISPATCH_EXCLUDED_AGENTS.intersection(agent_keys)
    if excluded:
        raise ValueError(
            f"Refusing to wire DELTA_DISPATCH_EXCLUDED_AGENTS into the delta-dispatch graph: {sorted(excluded)}"
        )

    specialist_runners = specialist_runners or {}
    router = PMOCommanderRouter(chat_agent)
    specialists = [SpecialistAgentExecutor(agent_key, specialist_runners.get(agent_key)) for agent_key in agent_keys]

    builder = WorkflowBuilder(start_executor=router)
    builder.add_multi_selection_edge_group(router, specialists, selection_func=select_by_router_decision)
    return builder.build()


async def dispatch_delta(workflow: Any, state: SwarmState) -> SwarmState:
    """Run one delta-dispatch cycle and fold the specialists' yielded
    `AgentExecutionOutput`s back into `SwarmState.execution_outputs`.
    """
    events = await workflow.run(state)
    outputs = [output for output in events.get_outputs() if isinstance(output, AgentExecutionOutput)]
    return state.with_outputs(outputs)


def build_default_chat_agent(*, temperature: float = 0.10) -> Agent:
    """Build the Router's `Agent` from the `AZURE_OPENAI_*` environment
    variables already used elsewhere in this project (see `.env`). Routing
    is a cheap classification task, so this prefers the mini deployment when
    one is configured.

    `agent_framework.openai.OpenAIChatClient` talks to Azure OpenAI directly
    when given `azure_endpoint`/`api_version` (there is no separate
    `AzureOpenAIChatClient` in this SDK version -- Azure and OpenAI share one
    client class).
    """
    from agent_framework.openai import OpenAIChatClient

    client = OpenAIChatClient(
        model=os.environ.get("AZURE_OPENAI_MINI_DEPLOYMENT_NAME") or os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
    )
    return Agent(
        client=client,
        name="PMOCommanderRouter",
        instructions=_ROUTER_SYSTEM_PROMPT,
        default_options={"temperature": temperature},
    )
