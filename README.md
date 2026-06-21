# 🛡️ ZATCA E-Invoicing Compliance - MCP Agent Harness

An enterprise-grade, standard-compliant Agentic Engineering harness built during the **5-Day of AI Agents Intensive Vibe Coding Course**. This project transitions traditional e-invoicing workflows into an interoperable, domain-bound multi-agent workforce by implementing the **Model Context Protocol (MCP)** and defining **Agent-to-Agent (A2A)** interaction boundaries.

---

## 🏗️ Project Architecture & Ecosystem

In alignment with modern agentic architectures, this repository moves away from fragile, bespoke single-agent monoliths and establishes a highly specialized, clean infrastructure:

1. **`server.js` (The MCP Server):** A secure, local background subprocess that communicates over standard I/O (`stdio`) via `JSON-RPC 2.0` protocol. It encapsulates cryptographic ZATCA TLV encoding and deterministic SQLite archiving to eliminate mathematical hallucinations.
2. **`agent_card.json` (The Agent Manifest):** A machine-readable profile defining the capabilities, security guardrails, and compliance bounds of the invoice specialist.
3. **`AGENTS.MD` (The Governance Layer):** Strict behavioral and prompt hygiene guidelines enforcing surgical edits and goal-driven validation loops for developer agents.

---

## 🛠️ Quick Start & Installation

### 1. Prerequisites
Ensure you have **Node.js** (v18+ recommended) installed on your environment.

### 2. Install Dependencies
Clone the repository, navigate into the backend repository, and initialize the environment:
```bash
npm install
