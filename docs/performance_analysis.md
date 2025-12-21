# AGiXT Backend Performance Analysis

## Test Date: December 20, 2024

## Summary - OPTIMIZATIONS COMPLETE ✅

After implementing performance optimizations, we achieved significant improvements in API response times.

## Latest Test Results (81 tests passed)

| Endpoint | Before | After | Improvement |
|----------|--------|-------|-------------|
| `get_providers` | 1350.9ms | **113.3ms** | **🔥 92% faster** |
| `get_agents` | 2050.9ms | **725.1ms** | **🔥 65% faster** |
| `get_user` (user_operations) | ~800-1000ms | **675.6ms** | **🔥 30%+ faster** |
| `get_agent_extensions` | 1726.9ms | **972.6ms** | **🔥 44% faster** |
| `get_agent_config` | 1634.7ms | **1274.6ms** | **🟢 22% faster** |
| `get_memories` | 1695.9ms | **1132.9ms** | **🟢 33% faster** |
| `get_extensions` | 724.5ms | **602.8ms** | **🟢 17% faster** |
| `get_agent_commands` | ~1000ms | **31.4ms** | **🔥 97% faster** |

## Startup Time Analysis

Added comprehensive startup timing instrumentation:

```
⏱️  STARTUP TIMING REPORT
======================================================================
  DB module import: 228.0ms
  Create tables: 3.0ms
  Migrations (total): ~78ms
  initialize_extension_tables: 2634.3ms  ⚠️ BOTTLENECK
  setup_default_scopes: 101.9ms
  setup_default_role_scopes: 588.0ms    ⚠️ SLOW
  seed_data import_all_data: 4840.7ms   (first start only)
  Uvicorn ready: 6535.0ms
----------------------------------------------------------------------
  TOTAL STARTUP TIME: 15,072ms (15.07s)
======================================================================
```

### Startup Bottlenecks Identified

| Component | Time | Notes |
|-----------|------|-------|
| `initialize_extension_tables` | 2.6s | Imports every extension module |
| `setup_default_role_scopes` | 588ms | Individual queries for each scope mapping |
| `seed_data import_all_data` | 4.8s | Only runs on first start |
| Uvicorn workers ready | 6.5s | 20 worker processes starting |

## Optimizations Implemented

### 1. Provider Caching (`Providers.py`) ✅
- Added module-level `_provider_cache` with 300s TTL
- Filesystem scan now only happens once every 5 minutes
- Cache is automatically refreshed on TTL expiry

### 2. Command Caching (`Agent.py`) ✅
- Added `_all_commands_cache` with TTL and `get_all_commands_cached()` function
- Commands (including chains) are queried once per hour
- Significant reduction in database queries

### 3. `get_agents()` Batch Query Optimization (`Agent.py`) ✅
- Replaced N+1 query pattern with batch queries
- Used SQLAlchemy `joinedload(AgentModel.settings)` for eager loading
- Moved onboarding checks to background queue via `enqueue_agent_onboarding()`
- Added `get_agents_lightweight()` for user endpoint (minimal fields only)

### 4. `get_agent_config()` Optimizations (`Agent.py`) ✅
- Consolidated 3 wallet setting queries into 1 single query with `IN` clause
- Optimized command lookup from O(n*m) to O(n+m) using a set for enabled command IDs
- Added company agent config caching with `get_company_agent_config_cached()`

### 5. `/v1/user` Smart Billing Optimization (`MagicalAuth.py`) ✅
- Created `get_user_preferences_smart()` method with intelligent billing checks
- **Fast token balance check** (DB query) is synchronous - blocks with 402 if no tokens AND billing enabled
- **Stripe subscription checks** now run in background threads when user has tokens
- Email verification sends asynchronously
- Critical paywall enforcement preserved while eliminating blocking Stripe API calls

### 6. `get_user_companies_with_roles()` Optimization (`MagicalAuth.py`) ✅
- Used `get_agents_lightweight()` instead of full `get_agents()` for each company
- Batch queries for company data

### 7. SSO Provider Caching (`Agent.py`) ✅
- Added `get_sso_providers_cached()` with 10-minute TTL
- Eliminates expensive filesystem scans and module loading on every `get_agent_extensions()` call
- Batch queries for OAuth provider lookups instead of N+1 pattern

### 8. Lightweight Commands Endpoint (`Agent.py`) ✅
- Added `get_agent_commands_only()` function that directly queries commands
- Bypasses full Agent initialization (was ~1000ms, now ~31ms)

### 9. Startup Timing Instrumentation (`run-local.py`) ✅
- Added `StartupTimer` class to track all initialization phases
- Timed each migration individually
- Poll-based uvicorn readiness check (faster than fixed sleep)
- Generates detailed timing report on startup

---

## Remaining Slow Endpoints (for future optimization)

| Endpoint | Time | Bottleneck |
|----------|------|------------|
| `execute_command` | ~1932ms | External AI call - inherently slow |
| `learn_text` | ~1708ms | Vector embedding operations |
| `get_agent_config` | ~1274ms | Wallet creation logic in hot path |
| `get_memories` | ~1132ms | Vector similarity search |

### Potential Future Optimizations

1. **`get_agent_config`**: Move wallet creation to agent creation time only
2. **`initialize_extension_tables`**: Lazy loading or cached extension model discovery
3. **`setup_default_role_scopes`**: Batch insert instead of individual queries
4. **Uvicorn workers**: Consider reducing worker count or using lazy initialization

---

## Original Analysis (for reference)
- Remove duplicate cleanup from hot path (run as background job)
- Use single query with filtering instead of multiple queries
- Cache command list (changes infrequently)

### 4. `get_agent_memories` (~1.7 seconds)

**Location:** Memory/vector search operations

**Problems:**
1. Vector similarity search is inherently expensive
2. No pagination limits on initial fetch
3. May be loading embeddings unnecessarily

**Recommended Fixes:**
- Add proper pagination and limit defaults
- Consider memory caching for recent queries
- Optimize vector index if not already done

### 5. `execute_command` (~1.5 seconds)

**Mostly expected** - commands involve actual work. However:
- Extension loading could be cached
- Agent initialization overhead (see #3)

### 6. `learn_text` (~1.3 seconds)

**Mostly expected** - involves embedding generation and storage. However:
- Batch embedding requests where possible
- Consider async processing for non-critical memories

## Quick Wins (Implement First)

### 1. Cache Provider List

```python
# Providers.py
_provider_cache = None
_provider_cache_time = 0
PROVIDER_CACHE_TTL = 300  # 5 minutes

def get_providers():
    global _provider_cache, _provider_cache_time
    if _provider_cache and (time.time() - _provider_cache_time) < PROVIDER_CACHE_TTL:
        return _provider_cache
    
    _provider_cache = list(_get_ai_provider_extensions().keys())
    _provider_cache_time = time.time()
    return _provider_cache
```

### 2. Eager Load Agent Settings

```python
# Agent.py get_agents()
from sqlalchemy.orm import joinedload

# Replace individual queries with:
agents_with_settings = (
    session.query(AgentModel)
    .options(joinedload(AgentModel.settings))
    .filter(AgentModel.user_id == user_data.id)
    .all()
)
```

### 3. Move Onboarding Out of get_agents ✅

The agent onboarding check should NOT run on every `get_agents` call. Instead:
- ✅ Onboarding now runs in background queue via `enqueue_agent_onboarding()`

### 4. Cache Commands List ✅

```python
# Agent.py - IMPLEMENTED
_all_commands_cache = {"data": None, "timestamp": 0, "ttl": 3600}

def get_all_commands_cached(session):
    global _all_commands_cache
    if _all_commands_cache["data"] and (time.time() - _all_commands_cache["timestamp"]) < _all_commands_cache["ttl"]:
        return _all_commands_cache["data"]
    # ... fetch and cache
```

## Remaining Optimizations (Future Work)

### 1. `get_agent_memories` (~1.4 seconds) - IN PROGRESS

Vector similarity search is inherently expensive. Potential improvements:
- Add proper pagination and limit defaults
- Consider memory caching for recent queries
- Optimize vector index if not already done

### 2. Database Indexing

Ensure proper indexes on:
- `agent_settings(agent_id)` 
- `agent_commands(agent_id)`
- `agents(user_id)`

### 3. Response Caching with Redis

For even better performance, consider:
- Redis caching for provider list
- Agent list per user (with invalidation on changes)

## Testing the Fixes

After implementing optimizations, re-run the timing tests:

```bash
cd /home/josh/repos/xtsys/AGiXT
/home/josh/repos/xtsys/.venv/bin/python -u tests/endpoint_tests.py
```

Look for the "ENDPOINT TIMING ANALYSIS" section to verify improvements.

## Performance Targets - STATUS

| Endpoint | Original | Current | Target | Status |
|----------|----------|---------|--------|--------|
| `get_providers` | 1350ms | **193ms** | <200ms | ✅ ACHIEVED |
| `get_agents` | 2050ms | **667ms** | <500ms | 🟡 Close |
| `get_agentconfig` | 1635ms | **1273ms** | <500ms | 🔴 Needs work |
| `get_agent_memories` | 1696ms | **1379ms** | <500ms | 🔴 Needs work |
| `learn_text` | 1300ms | **1022ms** | <800ms | 🟡 Close |
| `execute_command` | 1500ms | **1404ms** | <1000ms | 🟡 Close |
