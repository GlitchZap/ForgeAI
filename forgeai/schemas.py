"""Every artifact ForgeAI produces is one of these models, so it can be validated, diffed and reloaded."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- intake


class ClarifyingQuestions(BaseModel):
    questions: list[str] = Field(description="At most 5 questions whose answers would change the agent's design")


class QA(BaseModel):
    question: str
    answer: str
    assumed: bool = Field(False, description="True when no human answered and a default was assumed")


class Topic(BaseModel):
    name: str
    description: str
    source_hint: str = Field("documents", description="'documents' or 'tool:<tool_name>'")


class RequirementsDraft(BaseModel):
    title: str
    scope: str
    audience: str
    tone: str
    must_answer: list[Topic]
    must_refuse: list[str]


class GroundCheck(BaseModel):
    topic: str
    status: Literal["supported", "partial", "unsupported"]
    evidence: list[str] = []  # doc ids
    quote: str = ""
    note: str = ""


class Requirements(RequirementsDraft):
    clarifications: list[QA] = []
    groundability: list[GroundCheck] = []
    flags: list[str] = []


class GroundVerdict(BaseModel):
    status: Literal["supported", "partial", "unsupported"]
    quote: str = Field("", description="A short exact quote from the excerpts that supports the topic, empty if none")
    note: str = ""


# ---------------------------------------------------------------- agent definition


class RetrievalConfig(BaseModel):
    chunk_size: int = 900
    chunk_overlap: int = 150
    top_k: int = 4
    query_expansion: bool = False
    require_citation: bool = False


class PromptSections(BaseModel):
    """The system prompt is kept in sections so the optimizer can patch one without regenerating the rest."""
    role: str
    scope: str
    grounding_rules: str
    refusal_policy: str
    style: str
    tool_guidance: str = ""
    extra_rules: list[str] = []

    def render(self) -> str:
        parts = [self.role, "## Scope\n" + self.scope, "## Grounding rules\n" + self.grounding_rules,
                 "## When to refuse\n" + self.refusal_policy, "## Style\n" + self.style]
        if self.tool_guidance:
            parts.append("## Tools\n" + self.tool_guidance)
        if self.extra_rules:
            parts.append("## Additional rules\n" + "\n".join(f"- {r}" for r in self.extra_rules))
        return "\n\n".join(parts)


class ToolChoice(BaseModel):
    name: str
    reason: str


class OutputContract(BaseModel):
    format: Literal["json"] = "json"
    fields: dict[str, str] = {
        "answer": "string - the reply shown to the user",
        "citations": "list of chunk ids the answer relies on",
        "refused": "boolean - true when declining because the question is out of scope or unsupported",
        "refusal_reason": "string - short reason when refused, else empty",
    }


class AgentDefinition(BaseModel):
    name: str
    version: int = 0
    docs_path: str
    prompt: PromptSections
    retrieval: RetrievalConfig = RetrievalConfig()
    tools: list[ToolChoice] = []
    output_contract: OutputContract = OutputContract()
    must_refuse: list[str] = []

    @property
    def system_prompt(self) -> str:
        return self.prompt.render()


class PromptDraft(BaseModel):
    role: str
    scope: str
    grounding_rules: str
    refusal_policy: str
    style: str
    tool_guidance: str = ""


class ToolVote(BaseModel):
    needed: bool
    reason: str = Field(description="Which must-answer topic needs this tool, or why it is not needed")


# ---------------------------------------------------------------- runtime


class AgentReply(BaseModel):
    answer: str
    citations: list[str] = []
    refused: bool = False
    refusal_reason: str = ""


class ToolCall(BaseModel):
    tool: str = Field(description="Tool name, or 'none'")
    args: dict = {}


class Trace(BaseModel):
    """What the agent saw and did for one question - the judge and optimizer need this, not just the answer."""
    question: str
    retrieved: list[str]  # chunk ids
    retrieved_docs: list[str]
    tool_calls: list[dict] = []
    reply: AgentReply


# ---------------------------------------------------------------- evals

CaseKind = Literal["answerable", "multi_doc", "ambiguous", "out_of_scope", "tool"]


class EvalCase(BaseModel):
    id: str
    kind: CaseKind
    question: str
    should_refuse: bool = False
    expected_sources: list[str] = []
    key_facts: list[str] = []
    expected_tool: str | None = None
    split: Literal["dev", "holdout"] = "dev"
    origin: str = ""  # chunk ids / topic the case was generated from


class GeneratedQA(BaseModel):
    question: str
    key_facts: list[str] = Field(description="2-4 short facts copied VERBATIM from the excerpt")


class GeneratedQAList(BaseModel):
    items: list[GeneratedQA]


class GeneratedQuestions(BaseModel):
    questions: list[str]


class JudgeOut(BaseModel):
    facts_present: list[bool] = Field(description="One entry per expected fact, in the order given")
    unsupported_claims: list[str] = Field(description="Claims in the answer NOT supported by the context")


class CaseResult(BaseModel):
    case_id: str
    kind: CaseKind
    split: str
    passed: bool
    refused: bool
    refusal_ok: bool
    retrieval_hit: bool | None = None
    cited_hit: bool | None = None
    fact_recall_det: float | None = None
    fact_recall_llm: float | None = None
    grounded: bool | None = None
    judge_agreement: bool | None = None
    tool_ok: bool | None = None
    failure: Literal["retrieval_miss", "prompt_defect", "hallucination", "wrong_refusal"] | None = None
    notes: list[str] = []
    answer: str = ""
    # evidence for the UI's case trace: what the agent saw and did, and what each judge pass said
    trace: dict | None = None
    judge_passes: list[dict] = []


class Scorecard(BaseModel):
    iteration: int
    dev_pass_rate: float
    holdout_pass_rate: float
    overall_pass_rate: float
    by_kind: dict[str, float]
    failures: dict[str, int]
    judge_disagreement_rate: float
    tokens: int = 0
    seconds: float = 0.0
    results: list[CaseResult]


class SectionPatch(BaseModel):
    new_text: str
    rationale: str


class RulePatch(BaseModel):
    rule: str
    rationale: str


class ChangeLog(BaseModel):
    iteration: int
    category: str
    target: str
    before: str
    after: str
    rationale: str
    addressed_cases: list[str]
    score_before: float
    score_after: float | None = None
    kept: bool | None = None
