# SRL + RAG Overview

## Why Add Semantic Resolution Before Retrieval?

A RAG-only application commonly sends the user's wording directly into retrieval. In a civil-registration domain, that can be too broad because several services may share similar terms while having different procedural requirements.

La Dukca therefore uses a semantic-resolution concept before bounded retrieval.

## Simplified Comparison

### RAG-only

```text
query
  -> retrieval
  -> generation
```

### La Dukca approach

```text
citizen language
  -> semantic intent / condition resolution
  -> bounded service path
  -> RAG retrieval
  -> grounding validation
  -> answer composition
```

## Engineering Benefits

The separation makes it possible to reason about routing quality independently from retrieval and generation. It also helps reduce unrelated retrieval, cross-service contamination, and unsupported answer expansion.

## Multi-Turn Context

The same citizen can ask a follow-up question that would be ambiguous in isolation. Context handling therefore needs to preserve a valid prior service path while still allowing an explicit correction or topic change to replace it.

## Fail-Closed Behavior

If the system cannot establish a sufficiently grounded path, it should not compensate with fluent speculation. A deterministic insufficient-knowledge or clarification path is safer.

## What Is Not Published Here

This repository does not publish:

- protected routing rules;
- hidden or sealed test cases;
- internal acceptance matrices;
- canary datasets;
- shadow-probe datasets;
- qualification evidence;
- production-promotion criteria.

The goal is to explain the architecture while preserving the integrity of internal QA.
