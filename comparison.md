# AGiXT Endpoint Usage Comparison

This document tracks which AGiXT endpoints are actually being used by the frontend applications (Web and ESP32) vs what exists in the AGiXT backend.

## Summary

| Category | Backend Endpoints | Web Usage | ESP32 Usage |
|----------|------------------|-----------|-------------|
| Agent | 25 | 18 | 0 |
| Auth/User | 23 | 20 | 2 |
| Billing | 34 | 30 | 0 |
| Chain | 13 | 13 | 0 |
| Completions | 7 | 3 | 5 |
| Conversation | 38 | 26 | 3 |
| Extension | 9 | 4 | 0 |
| Memory | 17 | 6 | 0 |
| Prompt | 9 | 8 | 0 |
| Provider | 7 | 1 | 0 |
| Roles | 13 | 13 | 0 |
| Server Config | 17 | 12 | 0 |
| Tasks | 5 | 5 | 0 |
| Webhook | 17 | 13 | 0 |
| Health | 1 | 0 | 0 |

---

## Detailed Endpoint Analysis

### Agent Endpoints

| Endpoint | Method | Web Usage | ESP32 Usage | Notes |
|----------|--------|-----------|-------------|-------|
| `/v1/agent` | GET | ✅ (5+) | ❌ | Used in agent.ts, settings/page.tsx |
| `/v1/agent` | POST | ✅ (3+) | ❌ | Create agent - settings/page.tsx, CreateAgentDialog.tsx |
| `/v1/agent/import` | POST | ✅ | ❌ | SDK only |
| `/v1/agent/think` | POST | ❌ | ❌ | Not referenced in frontends |
| `/v1/agent/{agent_id}` | GET | ✅ (2+) | ❌ | agent.ts |
| `/v1/agent/{agent_id}` | PUT | ✅ (4+) | ❌ | settings/page.tsx, CreateAgentDialog.tsx |
| `/v1/agent/{agent_id}` | PATCH | ✅ | ❌ | SDK |
| `/v1/agent/{agent_id}` | DELETE | ✅ (2+) | ❌ | settings/page.tsx |
| `/v1/agent/{agent_id}/providers` | GET | ❌ | ❌ | Not used |
| `/v1/agent/{agent_id}/provider/{provider_name}` | DELETE | ❌ | ❌ | Not used |
| `/v1/agent/{agent_id}/persona` | GET | ✅ (3+) | ❌ | useTrainingData.ts, TrainingSection.tsx, OnboardingFlow.tsx |
| `/v1/agent/{agent_id}/persona` | PUT | ✅ (2+) | ❌ | TrainingSection.tsx, OnboardingFlow.tsx |
| `/v1/agent/{agent_id}/persona/{company_id}` | GET | ✅ | ❌ | useTrainingData.ts, TrainingSection.tsx |
| `/v1/agent/{agent_id}/persona/{company_id}` | PUT | ✅ | ❌ | TrainingSection.tsx |
| `/v1/agent/{agent_id}/commands` | PUT | ✅ | ❌ | SDK |
| `/v1/agent/{agent_id}/command` | GET | ✅ (3+) | ❌ | agent.ts, settings/page.tsx |
| `/v1/agent/{agent_id}/command` | POST | ✅ (4+) | ❌ | settings/page.tsx, chains/page.tsx, abilities/page.tsx |
| `/v1/agent/{agent_id}/command` | PATCH | ✅ | ❌ | SDK |
| `/v1/agent/{agent_id}/prompt` | POST | ✅ | ❌ | prompts/page.tsx |
| `/v1/agent/{agent_id}/extension/commands` | PATCH | ✅ (2+) | ❌ | settings/page.tsx, resource-guidance-card.tsx |
| `/v1/agent/{agent_id}/extensions` | GET | ✅ | ❌ | agent.ts |
| `/v1/agent/{agent_id}/browsed_links/{collection_number}` | DELETE | ❌ | ❌ | Not used |
| `/v1/agent/{agent_id}/browsed_links` | GET | ❌ | ❌ | Not used |
| `/v1/agent/{agent_id}/text_to_speech` | POST | ❌ | ❌ | Not used from frontends |
| `/v1/agent/{agent_id}/plan/task` | POST | ❌ | ❌ | Not used |
| `/v1/agent/{agent_id}/wallet` | GET | ✅ | ❌ | settings/page.tsx |
| `/v1/agent/{agent_id}/clone` | POST | ✅ | ❌ | settings/page.tsx |

### Auth/User Endpoints

| Endpoint | Method | Web Usage | ESP32 Usage | Notes |
|----------|--------|-----------|-------------|-------|
| `/v1/user` | POST | ✅ (2+) | ✅ | Register - register/page.tsx, agixt_client.c |
| `/v1/user` | GET | ✅ (5+) | ✅ | user.ts, middleware.tsx, team/page.tsx, agixt_client.cpp |
| `/v1/user` | PUT | ✅ (2+) | ❌ | user.ts, team/[id]/page.tsx |
| `/v1/user` | DELETE | ✅ | ❌ | SDK |
| `/v1/user/exists` | GET | ✅ | ❌ | user/page.tsx |
| `/v1/user/role` | PUT | ✅ (5+) | ❌ | team/page.tsx, team/[id]/page.tsx |
| `/v1/login` | POST | ✅ (2+) | ❌ | login/page.tsx |
| `/v1/logout` | POST | ❌ | ❌ | Not explicitly used |
| `/v1/user/mfa/email` | POST | ✅ (2+) | ❌ | login/page.tsx |
| `/v1/user/mfa/sms` | POST | ✅ | ❌ | SDK |
| `/v1/user/mfa/reset` | POST | ✅ | ❌ | SDK |
| `/v1/user/verify/email` | POST | ✅ (2+) | ❌ | user.ts, middleware.tsx |
| `/v1/user/verify/sms` | POST | ✅ | ❌ | SDK |
| `/v1/user/verify/mfa` | POST | ✅ | ❌ | SDK |
| `/v1/user/tos/accept` | POST | ✅ | ❌ | user.ts |
| `/v1/user/scopes` | GET | ✅ | ❌ | useRoles.ts |
| `/v1/user/{user_id}/custom-roles` | GET | ✅ | ❌ | useRoles.ts |
| `/v1/invitations` | GET | ✅ | ❌ | SDK |
| `/v1/invitations` | POST | ✅ | ❌ | team/page.tsx |
| `/v1/invitations/{company_id}` | GET | ✅ | ❌ | SDK |
| `/v1/invitation/{invitation_id}` | DELETE | ✅ | ❌ | team/page.tsx |
| `/v1/oauth` | GET | ✅ | ❌ | OAuth.tsx |
| `/v1/oauth2` | GET | ✅ (3+) | ❌ | settings/page.tsx |
| `/v1/oauth2/{provider}` | POST | ✅ (2+) | ❌ | settings/page.tsx, middleware.tsx |
| `/v1/oauth2/{provider}` | PUT | ✅ | ❌ | SDK |
| `/v1/oauth2/{provider}` | DELETE | ✅ (2+) | ❌ | settings/page.tsx |
| `/v1/oauth2/pkce-simple` | GET | ✅ (2+) | ❌ | settings/page.tsx, OAuth.tsx |
| `/v1/wallet/nonce` | GET | ✅ | ❌ | WalletAuth.tsx |
| `/v1/wallet/verify` | POST | ✅ | ❌ | WalletAuth.tsx |
| `/v1/wallet/session` | GET | ✅ | ❌ | settings/page.tsx |
| `/v1/wallet/disconnect` | POST | ✅ | ❌ | settings/page.tsx |

### Billing Endpoints

| Endpoint | Method | Web Usage | ESP32 Usage | Notes |
|----------|--------|-----------|-------------|-------|
| `/v1/billing/tokens/balance` | GET | ✅ | ❌ | billing.ts |
| `/v1/billing/tokens/quote` | POST | ✅ | ❌ | billing.ts |
| `/v1/billing/tokens/topup/crypto` | POST | ✅ | ❌ | billing.ts |
| `/v1/billing/tokens/topup/stripe` | POST | ✅ | ❌ | billing.ts |
| `/v1/billing/tokens/topup/stripe/confirm` | POST | ✅ | ❌ | billing.ts |
| `/v1/billing/tokens/warning/dismiss` | POST | ✅ | ❌ | billing.ts |
| `/v1/billing/tokens/should_warn` | GET | ✅ | ❌ | billing.ts |
| `/v1/billing/sync` | POST | ✅ | ❌ | billing.ts |
| `/v1/billing/config` | GET | ✅ | ❌ | billing.ts |
| `/v1/billing/currencies` | GET | ✅ | ❌ | billing.ts |
| `/v1/billing/quote` | POST | ✅ | ❌ | billing.ts |
| `/v1/billing/crypto/invoice` | POST | ✅ | ❌ | billing.ts |
| `/v1/billing/crypto/verify` | POST | ✅ | ❌ | billing.ts |
| `/v1/billing/stripe/payment-intent` | POST | ✅ | ❌ | billing.ts |
| `/v1/billing/transactions` | GET | ✅ | ❌ | billing.ts |
| `/v1/billing/subscription` | GET | ✅ | ❌ | billing.ts |
| `/v1/billing/usage` | GET | ❌ | ❌ | Not used |
| `/v1/billing/usage/totals` | GET | ✅ | ❌ | CompanyUsage.tsx |
| `/v1/billing/auto-topup` | GET | ✅ | ❌ | billing.ts |
| `/v1/billing/auto-topup` | POST | ✅ | ❌ | billing.ts |
| `/v1/billing/auto-topup` | PUT | ✅ | ❌ | billing.ts |
| `/v1/billing/auto-topup` | DELETE | ✅ | ❌ | billing.ts |
| `/v1/admin/companies` | GET | ✅ | ❌ | billing.ts |
| `/v1/admin/companies` | POST | ✅ | ❌ | billing.ts |
| `/v1/admin/companies/{company_id}` | DELETE | ✅ | ❌ | billing.ts |
| `/v1/admin/companies/{company_id}` | PATCH | ✅ | ❌ | billing.ts |
| `/v1/admin/companies/{company_id}/suspend` | POST | ✅ | ❌ | billing.ts |
| `/v1/admin/companies/{company_id}/unsuspend` | POST | ✅ | ❌ | billing.ts |
| `/v1/admin/companies/{company_id}/users` | POST | ✅ | ❌ | billing.ts |
| `/v1/admin/companies/{company_id}/users/{user_id}` | DELETE | ✅ | ❌ | billing.ts |
| `/v1/admin/companies/{company_id}/users/{user_id}/role` | PATCH | ✅ | ❌ | billing.ts |
| `/v1/admin/companies/merge` | POST | ✅ | ❌ | billing.ts |
| `/v1/admin/credit` | POST | ✅ | ❌ | billing.ts |
| `/v1/admin/users/{user_id}` | DELETE | ✅ | ❌ | billing.ts |
| `/v1/admin/stats` | GET | ✅ | ❌ | billing.ts |
| `/v1/admin/impersonate` | POST | ✅ | ❌ | billing.ts |
| `/v1/admin/export/companies` | GET | ✅ | ❌ | billing.ts |
| `/v1/admin/set-super-admin` | POST | ❌ | ❌ | Not used in frontend |
| `/v1/credit` | POST | ❌ | ❌ | Server-to-server only (requires AGIXT_API_KEY) |

### Chain Endpoints

| Endpoint | Method | Web Usage | ESP32 Usage | Notes |
|----------|--------|-----------|-------------|-------|
| `/v1/chains` | GET | ✅ | ❌ | SDK |
| `/v1/chain` | POST | ✅ | ❌ | SDK |
| `/v1/chain/import` | POST | ✅ | ❌ | SDK |
| `/v1/chain/{chain_id}` | GET | ✅ | ❌ | SDK |
| `/v1/chain/{chain_id}` | PUT | ✅ | ❌ | SDK |
| `/v1/chain/{chain_id}` | DELETE | ✅ | ❌ | SDK |
| `/v1/chain/{chain_id}/args` | GET | ✅ | ❌ | SDK |
| `/v1/chain/{chain_id}/step` | POST | ✅ | ❌ | SDK |
| `/v1/chain/{chain_id}/step/{step_number}` | PUT | ✅ | ❌ | SDK |
| `/v1/chain/{chain_id}/step/{step_number}` | DELETE | ✅ | ❌ | SDK |
| `/v1/chain/{chain_id}/step/move` | PATCH | ✅ | ❌ | SDK |
| `/v1/chain/{chain_id}/run` | POST | ✅ | ❌ | SDK |
| `/v1/chain/{chain_id}/run/step/{step_number}` | POST | ✅ | ❌ | SDK |

### Completions Endpoints (OpenAI-Compatible)

| Endpoint | Method | Web Usage | ESP32 Usage | Notes |
|----------|--------|-----------|-------------|-------|
| `/v1/chat/completions` | POST | ✅ (5+) | ✅ (6+) | **Most used endpoint** - conversation.tsx, tickets/page.tsx, resource-guidance-card.tsx, agixt_client.c |
| `/v1/mcp/chat/completions` | POST | ❌ | ❌ | Not used |
| `/v1/embeddings` | POST | ❌ | ❌ | Not used directly from frontends |
| `/v1/audio/transcriptions` | POST | ❌ | ✅ | agixt_client.c, agixt_client.cpp |
| `/v1/audio/translations` | POST | ❌ | ❌ | Not used |
| `/v1/audio/speech` | POST | ❌ | ✅ | agixt_client.cpp (old) |
| `/v1/images/generations` | POST | ❌ | ❌ | Not used |

### Conversation Endpoints

| Endpoint | Method | Web Usage | ESP32 Usage | Notes |
|----------|--------|-----------|-------------|-------|
| `/v1/conversations` | GET | ✅ | ❌ | conversation.ts |
| `/v1/conversation` | GET | ✅ | ❌ | conversation.ts |
| `/v1/conversation` | POST | ✅ | ❌ | chat-input-new.tsx |
| `/v1/conversation/{conversation_id}` | GET | ✅ | ❌ | SDK |
| `/v1/conversation/{conversation_id}` | DELETE | ✅ | ❌ | SDK |
| `/v1/conversation/{conversation_id}` | PUT | ❌ | ❌ | Not used |
| `/v1/conversation/{conversation_id}/message` | POST | ❌ | ❌ | Not used (uses chat/completions instead) |
| `/v1/conversation/{conversation_id}/message/{message_id}` | PUT | ❌ | ❌ | Not used |
| `/v1/conversation/{conversation_id}/message/{message_id}` | DELETE | ❌ | ❌ | Not used |
| `/v1/conversation/{conversation_id}/messages-after/{message_id}` | DELETE | ✅ | ❌ | conversation.tsx via deleteMessagesAfter |
| `/v1/conversation/{conversation_id}/workspace` | GET | ✅ | ❌ | conversation.ts |
| `/v1/conversation/{conversation_id}/workspace/upload` | POST | ✅ | ✅ | conversation.ts, agixt_client.c |
| `/v1/conversation/{conversation_id}/workspace/folder` | POST | ✅ | ❌ | conversation.ts |
| `/v1/conversation/{conversation_id}/workspace/item` | DELETE | ✅ | ❌ | conversation.ts |
| `/v1/conversation/{conversation_id}/workspace/item` | PUT | ✅ | ❌ | conversation.ts |
| `/v1/conversation/{conversation_id}/workspace/download` | GET | ✅ | ❌ | conversation.ts |
| `/v1/conversation/{conversation_id}/tts/{message_id}` | GET | ✅ | ❌ | Message/Actions.tsx |
| `/v1/conversation/{conversation_id}/stop` | POST | ❌ | ❌ | Not used |
| `/v1/conversations/stop` | POST | ❌ | ❌ | Not used |
| `/v1/conversations/active` | GET | ❌ | ❌ | Not used |
| `/v1/conversation/{conversation_id}/remote-command-result` | POST | ❌ | ❌ | Not used |
| `/v1/conversation/{conversation_id}/share` | POST | ✅ | ❌ | conversation.ts |
| `/v1/conversations/shared` | GET | ✅ | ❌ | conversation.ts |
| `/v1/conversation/share/{share_token}` | DELETE | ✅ | ❌ | conversation.ts |
| `/v1/conversation/import-shared/{share_token}` | POST | ✅ | ❌ | shared/[token]/page.tsx |
| `/v1/conversation/fork/{conversation_id}/{message_id}` | POST | ✅ | ❌ | Message/Actions.tsx |
| `/v1/conversation/{conversation_id}/stream` | WebSocket | ✅ | ✅ | useConversationWebSocketStable.ts, agixt_client.cpp |
| `/v1/user/notifications` | WebSocket | ✅ | ❌ | useUserNotifications.ts |

### Extension Endpoints

| Endpoint | Method | Web Usage | ESP32 Usage | Notes |
|----------|--------|-----------|-------------|-------|
| `/v1/extensions/settings` | GET | ❌ | ❌ | Not used from frontend |
| `/v1/extensions/{command_name}/args` | GET | ❌ | ❌ | Not used |
| `/v1/extension/categories` | GET | ✅ | ❌ | OnboardingFlow.tsx |
| `/v1/extension/categories/summary` | GET | ❌ | ❌ | Not used |
| `/v1/extension/category/{category_id}` | GET | ❌ | ❌ | Not used |
| `/v1/extensions` | POST | ❌ | ❌ | Not used |
| `/v1/extensions/category/{category_id}` | GET | ❌ | ❌ | Not used |

### Memory Endpoints

| Endpoint | Method | Web Usage | ESP32 Usage | Notes |
|----------|--------|-----------|-------------|-------|
| `/v1/agent/{agent_id}/memory/{collection_number}/query` | POST | ❌ | ❌ | Not used |
| `/v1/agent/{agent_id}/memory/export` | GET | ✅ | ❌ | SDK |
| `/v1/agent/{agent_id}/memory/import` | POST | ✅ | ❌ | SDK |
| `/v1/agent/{agent_id}/learn/text` | POST | ❌ | ❌ | Not used |
| `/v1/agent/{agent_id}/learn/file` | POST | ✅ | ❌ | TrainingSection.tsx, OnboardingFlow.tsx |
| `/v1/agent/{agent_id}/learn/file/{company_id}` | POST | ✅ | ❌ | TrainingSection.tsx |
| `/v1/agent/{agent_id}/learn/url` | POST | ✅ | ❌ | TrainingSection.tsx, OnboardingFlow.tsx |
| `/v1/agent/{agent_id}/memory` | DELETE | ❌ | ❌ | Not used |
| `/v1/agent/{agent_id}/memory/{collection_number}` | DELETE | ✅ | ❌ | SDK |
| `/v1/agent/{agent_id}/memory/{collection_number}/{memory_id}` | DELETE | ❌ | ❌ | Not used |
| `/v1/agent/{agent_id}/memory/dataset` | POST | ❌ | ❌ | Not used |
| `/v1/agent/{agent_id}/dpo` | POST | ❌ | ❌ | Not used |
| `/v1/agent/{agent_id}/memory/dataset/{dataset_name}/finetune` | DELETE | ❌ | ❌ | Not used |
| `/v1/agent/{agent_id}/memories/external_source` | POST | ❌ | ❌ | Not used |
| `/v1/agent/{agent_id}/memory/external_sources/{collection_number}` | GET | ✅ | ❌ | useTrainingData.ts |
| `/v1/agent/{agent_id}/memory/external_sources/{collection_number}/{company_id}` | GET | ✅ | ❌ | useTrainingData.ts |
| `/v1/agent/{agent_id}/memory/external_source/{collection_number}/{source}` | DELETE | ✅ | ❌ | TrainingSection.tsx |
| `/v1/agent/{agent_id}/feedback` | POST | ✅ | ❌ | SDK |

### Prompt Endpoints

| Endpoint | Method | Web Usage | ESP32 Usage | Notes |
|----------|--------|-----------|-------------|-------|
| `/v1/prompts` | GET | ✅ | ❌ | prompt.ts |
| `/v1/prompt/categories` | GET | ✅ | ❌ | prompt.ts |
| `/v1/prompt/all` | GET | ✅ | ❌ | prompt.ts |
| `/v1/prompt/category/{category_id}` | GET | ❌ | ❌ | Not used |
| `/v1/prompt` | POST | ✅ | ❌ | SDK |
| `/v1/prompt/{prompt_id}` | GET | ✅ | ❌ | prompt.ts |
| `/v1/prompt/{prompt_id}` | PUT | ✅ | ❌ | SDK |
| `/v1/prompt/{prompt_id}` | DELETE | ✅ | ❌ | SDK |
| `/v1/prompt/{prompt_id}/args` | GET | ✅ | ❌ | prompt.ts |

### Provider Endpoints

| Endpoint | Method | Web Usage | ESP32 Usage | Notes |
|----------|--------|-----------|-------------|-------|
| `/v1/providers` | GET | ✅ | ❌ | provider.ts |
| `/api/provider` | GET | ❌ | ❌ | Not used |
| `/api/provider/{provider_name}` | GET | ❌ | ❌ | Not used |
| `/api/providers` | GET | ❌ | ❌ | Not used |
| `/api/providers/service/{service}` | GET | ❌ | ❌ | Not used |
| `/api/embedding_providers` | GET | ❌ | ❌ | Not used |
| `/api/embedders` | GET | ❌ | ❌ | Not used |

### Roles Endpoints

| Endpoint | Method | Web Usage | ESP32 Usage | Notes |
|----------|--------|-----------|-------------|-------|
| `/v1/scopes` | GET | ✅ | ❌ | useRoles.ts |
| `/v1/scopes/category/{category}` | GET | ❌ | ❌ | Not used |
| `/v1/user/scopes` | GET | ✅ | ❌ | useRoles.ts |
| `/v1/roles` | GET | ✅ | ❌ | useRoles.ts |
| `/v1/roles` | POST | ❌ | ❌ | Not used from frontend |
| `/v1/roles/{role_id}` | GET | ❌ | ❌ | Not used |
| `/v1/roles/{role_id}` | PUT | ❌ | ❌ | Not used |
| `/v1/roles/{role_id}` | DELETE | ❌ | ❌ | Not used |
| `/v1/user/custom-role` | POST | ❌ | ❌ | Not used |
| `/v1/user/{user_id}/custom-role/{custom_role_id}` | DELETE | ❌ | ❌ | Not used |
| `/v1/user/{user_id}/custom-roles` | GET | ✅ | ❌ | useRoles.ts |
| `/v1/default-roles` | GET | ✅ | ❌ | useRoles.ts |
| `/v1/default-roles/{role_id}/scopes` | GET | ❌ | ❌ | Not used |

### Server Config Endpoints

| Endpoint | Method | Web Usage | ESP32 Usage | Notes |
|----------|--------|-----------|-------------|-------|
| `/v1/server/config/public` | GET | ✅ | ❌ | serverConfig.ts |
| `/v1/server/config` | GET | ✅ | ❌ | serverConfig.ts |
| `/v1/server/config` | PUT | ✅ | ❌ | serverConfig.ts |
| `/v1/server/config/{config_name}` | GET | ✅ | ❌ | serverConfig.ts |
| `/v1/server/config/{config_name}` | PUT | ✅ | ❌ | serverConfig.ts |
| `/v1/server/config/categories` | GET | ✅ | ❌ | serverConfig.ts |
| `/v1/server/extension-settings` | GET | ✅ | ❌ | serverConfig.ts |
| `/v1/server/extension-settings` | PUT | ✅ | ❌ | serverConfig.ts |
| `/v1/server/extension-settings/{extension_name}/{setting_key}` | DELETE | ✅ | ❌ | serverConfig.ts |
| `/v1/server/extension-commands` | GET | ✅ | ❌ | serverConfig.ts |
| `/v1/server/extension-commands` | PUT | ✅ | ❌ | serverConfig.ts |
| `/v1/server/extension-commands/{extension_name}/{command_name}` | DELETE | ✅ | ❌ | serverConfig.ts |
| `/v1/server/oauth-providers` | GET | ✅ | ❌ | serverConfig.ts |
| `/v1/server/oauth-providers` | PUT | ✅ | ❌ | serverConfig.ts |
| `/v1/company/{company_id}/storage` | GET | ✅ | ❌ | team/page.tsx, companies/[id]/page.tsx |
| `/v1/company/{company_id}/storage` | PUT | ✅ | ❌ | team/page.tsx |
| `/v1/company/{company_id}/storage` | DELETE | ❌ | ❌ | Not used |

### Companies Endpoints

| Endpoint | Method | Web Usage | ESP32 Usage | Notes |
|----------|--------|-----------|-------------|-------|
| `/v1/companies` | GET | ✅ | ❌ | user.ts, lib/xts.ts |
| `/v1/companies` | POST | ✅ | ❌ | team/page.tsx, lib/xts.ts |
| `/v1/companies/{company_id}` | GET | ✅ | ❌ | lib/xts.ts |
| `/v1/companies/{company_id}` | PUT | ✅ | ❌ | SDK |
| `/v1/companies/{company_id}` | PATCH | ✅ | ❌ | lib/xts.ts |
| `/v1/companies/{company_id}` | DELETE | ✅ | ❌ | SDK, lib/xts.ts |
| `/v1/companies/{company_id}/extensions` | GET | ✅ | ❌ | company.ts |
| `/v1/companies/{company_id}/command` | PATCH | ✅ | ❌ | abilities/page.tsx |
| `/v1/companies/{company_id}/users/{user_id}` | DELETE | ✅ | ❌ | team/page.tsx |

### Task Endpoints

| Endpoint | Method | Web Usage | ESP32 Usage | Notes |
|----------|--------|-----------|-------------|-------|
| `/v1/task` | POST | ✅ | ❌ | tasks/create/page.tsx, tasks/page.tsx |
| `/v1/task` | PUT | ✅ | ❌ | tasks/page.tsx |
| `/v1/task` | DELETE | ✅ | ❌ | tasks/page.tsx |
| `/v1/reoccurring_task` | POST | ✅ | ❌ | tasks/create/page.tsx, tasks/page.tsx |
| `/v1/tasks` | GET | ✅ | ❌ | tasks/page.tsx |
| `/v1/tasks/due` | GET | ❌ | ❌ | Not used |

### Webhook Endpoints

| Endpoint | Method | Web Usage | ESP32 Usage | Notes |
|----------|--------|-----------|-------------|-------|
| `/v1/webhook/{webhook_id}` | POST | ❌ | ❌ | External webhook receiver (called by external systems) |
| `/api/webhooks/incoming` | POST | ✅ | ❌ | hooks.ts, sdk.ts - Create incoming webhook |
| `/api/webhooks/incoming` | GET | ✅ | ❌ | hooks.ts, sdk.ts - List incoming webhooks |
| `/api/webhooks/incoming/{webhook_id}` | GET | ✅ | ❌ | hooks.ts, sdk.ts - Get single incoming webhook |
| `/api/webhooks/incoming/{webhook_id}` | PUT | ✅ | ❌ | hooks.ts, sdk.ts - Update incoming webhook |
| `/api/webhooks/incoming/{webhook_id}` | DELETE | ✅ | ❌ | hooks.ts, sdk.ts - Delete incoming webhook |
| `/api/webhooks/outgoing` | POST | ✅ | ❌ | hooks.ts, sdk.ts - Create outgoing webhook |
| `/api/webhooks/outgoing` | GET | ✅ | ❌ | hooks.ts, sdk.ts - List outgoing webhooks |
| `/api/webhooks/outgoing/{webhook_id}` | GET | ✅ | ❌ | hooks.ts, sdk.ts - Get single outgoing webhook |
| `/api/webhooks/outgoing/{webhook_id}` | PUT | ✅ | ❌ | hooks.ts, sdk.ts - Update outgoing webhook |
| `/api/webhooks/outgoing/{webhook_id}` | DELETE | ✅ | ❌ | hooks.ts, sdk.ts - Delete outgoing webhook |
| `/api/webhooks/event-types` | GET | ✅ | ❌ | hooks.ts, sdk.ts - List available event types |
| `/api/webhooks/stats` | GET | ❌ | ❌ | Not used (global stats) |
| `/api/webhooks/logs` | GET | ❌ | ❌ | Not used (global logs) |
| `/api/webhooks/test/{webhook_id}` | POST | ✅ | ❌ | sdk.ts - Test outgoing webhook |
| `/api/webhooks/{webhook_id}/statistics` | GET | ✅ | ❌ | hooks.ts, sdk.ts - Get webhook stats |
| `/api/webhooks/{webhook_id}/logs` | GET | ✅ | ❌ | hooks.ts, sdk.ts - Get webhook logs |

### Health Endpoint

| Endpoint | Method | Web Usage | ESP32 Usage | Notes |
|----------|--------|-----------|-------------|-------|
| `/health` | GET | ❌ | ❌ | Not explicitly used in frontends |

---

## Unused Backend Endpoints (Candidates for Review)

These endpoints exist in the backend but are **not used** by any frontend:

### Agent
- `/v1/agent/think` - Agent thinking/reflection endpoint
- `/v1/agent/{agent_id}/providers` - Get agent providers
- `/v1/agent/{agent_id}/provider/{provider_name}` - Delete provider from agent
- `/v1/agent/{agent_id}/browsed_links*` - Browsed links management
- `/v1/agent/{agent_id}/text_to_speech` - Direct TTS (frontends use conversation TTS)
- `/v1/agent/{agent_id}/plan/task` - Task planning

### Completions
- `/v1/mcp/chat/completions` - MCP chat completions
- `/v1/embeddings` - Direct embeddings (used internally)
- `/v1/audio/translations` - Audio translation
- `/v1/images/generations` - Image generation

### Conversation
- `/v1/conversation/{conversation_id}/message*` - Direct message management (not used, chat/completions used instead)
- `/v1/conversation/{conversation_id}/stop` - Stop conversation
- `/v1/conversations/stop` - Stop all conversations
- `/v1/conversations/active` - Get active conversations
- `/v1/conversation/{conversation_id}/remote-command-result` - Remote command results

### Extension
- Most extension endpoints are not directly used from frontends

### Memory
- `/v1/agent/{agent_id}/memory/{collection_number}/query` - Memory query
- `/v1/agent/{agent_id}/learn/text` - Learn from text
- `/v1/agent/{agent_id}/memory` - Delete all memories
- `/v1/agent/{agent_id}/memory/dataset*` - Dataset management
- `/v1/agent/{agent_id}/dpo` - DPO training

### Roles
- Most role management endpoints (create, update, delete roles)
- Custom role management

### Webhooks
- `/v1/webhook/{webhook_id}` - External receiver (called by external systems, not frontend)
- `/api/webhooks/stats` - Global webhook stats (not used, per-webhook stats are used)
- `/api/webhooks/logs` - Global webhook logs (not used, per-webhook logs are used)

### Tasks
- `/v1/tasks/due` - Get due tasks

### Billing
- `/v1/admin/set-super-admin` - Set super admin
- `/v1/credit` - Server-to-server credit endpoint (not for frontend use - requires AGIXT_API_KEY)
- `/v1/billing/usage` - Usage details (only totals used)

---

## ESP32 Specific Usage

The ESP32 client is focused on voice interaction and has minimal endpoint usage:

1. **Authentication**: `/v1/user` (GET) - Verify authentication
2. **Chat**: `/v1/chat/completions` (POST) - Main chat interaction
3. **Audio**: `/v1/audio/transcriptions` (POST) - Speech-to-text
4. **Audio**: `/v1/audio/speech` (POST) - Text-to-speech
5. **Files**: `/v1/conversation/{id}/workspace/upload` (POST) - Upload audio files
6. **Streaming**: `/v1/conversation/{id}/stream` (WebSocket) - Real-time responses

---

## Frontend-Only Endpoints (xts.ts - Not AGiXT)

These endpoints are called from the web frontend but go to a separate XTS server (not AGiXT):

- `/v1/assets/*` - Asset management
- `/v1/machines/*` - Machine management
- `/v1/machine/*` - Machine control
- `/v1/asset-templates/*` - Asset templates
- `/v1/contacts/*` - Contact management
- `/v1/residents/*` - Resident management
- `/v1/notes/*` - Notes
- `/v1/medications/*` - Medications
- `/v1/tasks/*` (XTS version) - Task management
- `/v1/vitals/*` - Vitals tracking
- `/v1/documents/*` - Document management
- `/v1/secrets/*` - Secret management
- `/v1/tickets/*` - Ticket management

---

## Recommendations

1. **Review** `/v1/agent/think` - potentially valuable for complex reasoning
2. **Consider adding** ESP32 support for more endpoints if needed
3. **Document** the MCP chat completions endpoint purpose
4. **Consider UI** for memory/dataset management endpoints
5. **Consider adding** global webhook stats/logs to the webhooks page

---

*Last updated: December 20, 2024*
