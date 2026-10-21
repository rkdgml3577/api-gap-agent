"""Human-in-the-loop approval gate for finished findings.

The agent calls `approver.review(findings, context)` right before a run is
reported as completed. The return value decides whether the result stands or
goes back to the model for revision:

    {"approved": bool, "feedback": str, "by": str}

This is a deliberate seam. Today the approver is a person (HumanApprover) or a
pass-through (AutoApprover). Later an LLM judge can implement the SAME method and
be dropped in with no change to the graph — e.g. an LLMApprover that scores the
findings and returns approved/feedback. Keep review()'s signature stable.
"""
import asyncio
import os


class AutoApprover:
    """Default: approve everything. Keeps runs non-interactive and unchanged."""

    async def review(self, findings, context):
        return {"approved": True, "feedback": "", "by": "auto"}


class HumanApprover:
    """Pause the run and wait for a person to approve or reject via the API.

    The run coroutine awaits a future kept in a store (keyed by run_id) that
    lives outside the serializable run dict; the HTTP approve endpoint resolves
    it. A timeout rejects so a run never hangs forever.
    """

    def __init__(self, run_id, emit, store, timeout=None):
        self.run_id = run_id
        self.emit = emit
        self.store = store
        self.timeout = timeout if timeout is not None else float(os.getenv("APPROVAL_TIMEOUT", "600"))

    async def review(self, findings, context):
        future = asyncio.get_event_loop().create_future()
        self.store[self.run_id] = future
        await self.emit({"type": "approval_request", "findings": findings})
        try:
            decision = await asyncio.wait_for(future, timeout=self.timeout)
        except asyncio.TimeoutError:
            decision = {"approved": False,
                        "feedback": "Approval timed out. Re-check evidence and resubmit.",
                        "by": "timeout"}
        finally:
            self.store.pop(self.run_id, None)
        decision.setdefault("by", "human")
        decision.setdefault("feedback", "")
        return decision


def build_approver(run_id, emit, store):
    """Pick the approver from APPROVAL_MODE (auto|human). Future: |llm."""
    mode = os.getenv("APPROVAL_MODE", "auto").lower()
    if mode == "human":
        return HumanApprover(run_id, emit, store)
    return AutoApprover()
