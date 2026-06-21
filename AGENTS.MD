# AGENTS.MD - Coding Agent Governance & Vibe Coding Guidelines

This document establishes the strict behavioral guidelines and architectural constraints for all development agents operating within the **Programmer Farmer Lab** environment. All agent inferences must align with these principles to ensure safety, precision, and zero-hallucination execution.

---

## 1. Core Operating Principles

### 🧠 Think Deeply Before Coding
* Explicitly state your assumptions, surface structural tradeoffs, and map out edge cases before emitting any code blocks.
* Halt and immediately request human clarification the moment you encounter ambiguity rather than guessing silently or making creative assumptions.

### ✂️ Surgical Code Modification
* Make highly surgical changes by restricting your updates exclusively to the exact lines required to fulfill the user request.
* Maintain the existing codebase style, spacing, and formatting perfectly.
* Leave adjacent, unbroken code completely untouched unless your changes directly orphaned an import or a variable.

### 📉 Minimum Viable Code (MVC)
* Write only the absolute minimum amount of code required to solve the immediate problem at hand.
* Strictly avoid speculative features, unrequested abstractions, or predictive configurations. Keep the footprint small and readable.

### 🏁 Goal-Driven Verification Loop
* Approach every task through goal-driven execution by breaking down the request into a clear, step-by-step plan with strong success criteria.
* Run internal validation loops or test verification incrementally until the specific target goal is strictly met.

---

## 2. Protocol & Interoperability Standards

### 🔌 Model Context Protocol (MCP) Integration
* **Standard Transport:** All local tool integrations must consume or expose tools via the standardized Model Context Protocol (MCP) over `stdio` using `JSON-RPC 2.0` packets.
* **No Bespoke Wrappers:** Avoid writing fragile, ad-hoc REST API wrappers. Look for pre-built or approved MCP server registry configurations first.
* **Clean Context Windows:** Practice prompt hygiene. Tools should be dynamically queried or referenced; do not pollute the core system instruction context window with massive static JSON representations.

### 📻 Agent-to-Agent (A2A) Orchestration
* **Distributed Microservices over Monoliths:** Do not compile a "Swiss Army knife" single agent monolith. Divide complex workflows into specialized, domain-bound sub-agents.
* **Identity Manifests:** Every specialist agent must be equipped with a valid `agent_card.json` that details its machine-readable identity, core capabilities, and interaction schemas.
* **Stateless Delegation:** Use clear collaboration semantics. If an external contractor agent hits an interrupted or multi-turn state, isolate the conversational context rather than introducing unstructured loops into the main coordinator flow.

---

## 3. Security, Auditing, and Safety Guardrails

* **Environment-Based Credentials:** Never paste or hardcode API keys, authentication tokens, or private cryptographic secrets directly into prompt blocks or scripts. Use environment variables.
* **Safe Sandbox Testing:** Connect the agent strictly to non-production development environments populated with obfuscated or mock data.
* **Human-In-The-Loop (HITL):** Crucial actions—especially data mutations, payment executions, or compliance signatures—must display tool inputs to a human operator for explicit validation before calling the target server.

---

*Compiled in compliance with Google's Agent Tools & Interoperability Framework (May 2026).*
