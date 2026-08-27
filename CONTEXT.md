# llm-gateway

Self-hosted gateway where users create, share, and run their own tool-using agents on top of existing chat, provider-routing, and memory infrastructure.

## Language

### Agents

**Agent**:
A user-created configuration for a tool-using assistant: name, description, instructions (system prompt), model/provider selection, allowed-tool list, optional knowledge, and visibility flag. Not code — composition of existing primitives.
_Avoid_: bot, assistant (in the generic model sense)

**Agent Chat**:
A conversation bound to an Agent (`conversations.agent_id` set). General chat has `agent_id` null. Scoped in UI and memory retrieval.
_Avoid_: thread (overloaded)

**Capability**:
A dangerous tool class (code execution, web browsing) that requires both a global master switch and a per-user grant before an Agent may use it.
_Avoid_: permission (the user-level grant is a permission; capability is the class)

**Direct-shared instance (versioned)**:
Marketplace sharing model where installing creates a pointer to the same Agent row. Owner publishes a new version; installers explicitly upgrade their pinned version.
_Avoid_: fork, clone (in the marketplace sense)

**Install**:
A user's pointer to a public Agent at a pinned version. Not a copy.
_Avoid_: subscription, fork

**Marketplace**:
Browsable listing of public Agents. Anyone can install; only the owner can publish a new version.

### Execution

**Workspace**:
Per-running-user, per-Agent git-backed folder where the Agent's files live and code execution happens. On named volume `workspaces:/workspaces` at `workspaces/{user_id}/{agent_id}`.
_Avoid_: drive, sandbox

**Sandbox**:
Isolated execution environment (the `sandbox` service) that runs shell commands inside the Workspace. Reached via HTTP `POST /exec`.
_Avoid_: container (too generic), workspace

**File Edit**:
A mutating tool call: either `edit_patch` (unified diff) or `edit_lines` (hashline replacement). Validated against current per-line hashes; mismatch is a conflict.
_Avoid_: patch (one of two forms)

**Undo**:
Reversal of a File Edit via its `file_edits` audit row plus a git revert of the Workspace commit.

### Creation

**Agent Builder — Smart Suggest**:
Button in AgentForm that drafts name, description, instructions, and suggested tools/model from a goal string. Result prefills the editable form.
_Avoid_: builder chat (the chat-based builder was rejected)

## Architecture decisions

The deep-module seams are documented as ADRs in `docs/adr/`:
- `0005-agent-runtime.md` — `AgentRuntime.run(ctx)` owns the loop/budget/prune/dispatch; no DB crosses the seam.
- `0006-provider-router.md` — `ProviderRouter.resolve()` is the single pinned→default→fallback decision.
- `0007-agent-events.md` — `lib/agent-events.ts` owns the typed SSE union + FileEditResult parsing.
- `0008-workspace.md` — `WorkspaceStore` owns path security (the one 422 seam) and edit/undo.
