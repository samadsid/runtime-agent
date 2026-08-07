# AGENTS.md

# AI Commerce Agent

This file contains instructions for AI coding assistants (Codex, ChatGPT, Claude Code, Cursor, etc.) working on this repository.

---

# Project Goal

Build a production-ready, domain-agnostic AI Commerce Runtime.

The runtime should support multiple business domains through capabilities without changing the runtime architecture.

Current domain:
- Commerce

Future domains:
- ERP
- CRM
- Inventory
- Banking
- Healthcare

---

# Architecture Principles

Always follow Clean Architecture.

Dependencies must point inward.

Never allow framework code to leak into the domain layer.

Business logic must remain framework-independent.

---

# Technology Stack

Backend
- Python
- FastAPI
- Pydantic v2

AI
- LangGraph
- LangChain (adapter only)
- Ollama
- Qwen 2.5

Database
- PostgreSQL

Dependency Management
- requirements.txt

---

# Runtime Layers

API

↓

CommerceRuntime

↓

CommerceGraph (LangGraph)

↓

Planner

↓

CommandHandler

↓

Capability

---

# Important Rules

## Do NOT

- Put LangGraph imports inside business logic.
- Put LangChain messages inside domain models.
- Couple capabilities to LangGraph.
- Add graph nodes for every capability.
- Create duplicate models.
- Use generic dicts when typed models exist.
- Redesign architecture without updating docs.

---

## Always

- Keep business logic framework independent.
- Use adapters at framework boundaries.
- Keep capabilities small.
- Keep nodes orchestration-only.
- Keep graph state durable.

---

# Current Graph

START

↓

PlannerNode

↓

ExecuteNode

↓

END

---

# Current State

CommerceGraphState contains

- conversation_id
- messages
- command
- session (planned)

Messages are conversation history.

Session represents business state.

---

# Memory

Conversation history is stored using LangGraph checkpoints.

Never implement custom memory unless there is a demonstrated need.

---

# Session

CommerceSession is the future source of truth for business context.

Conversation history is NOT business state.

---

# Development Rules

Before changing architecture:

1. Read docs/architecture.md
2. Read docs/decisions.md
3. Read docs/current-status.md

Do not redesign frozen architecture.

---

# Coding Style

- Strong typing
- Small classes
- Dependency injection
- Immutable domain models when possible
- Composition over inheritance
- Prefer explicit code over magic

---

# Goal

Every new capability should be added without changing:

- CommerceRuntime
- CommerceGraph
- Planner