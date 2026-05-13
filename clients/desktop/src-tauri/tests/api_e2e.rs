//! End-to-end tests for the AGiXT REST helpers in `api.rs`.
//!
//! Each test stands up an in-process `wiremock` HTTP server posing as the
//! AGiXT backend, points the client at it, and asserts that
//! request/response shapes match what the real backend would emit.
//!
//! These are full network round-trips — no mocking inside the client — so
//! they catch regressions in URL construction, JSON shape parsing, and
//! authorization header handling.

use agixt_desktop_lib::api;
use serde_json::json;
use wiremock::matchers::{bearer_token, method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

#[tokio::test]
async fn list_companies_parses_bare_array() {
    let server = MockServer::start().await;

    Mock::given(method("GET"))
        .and(path("/v1/companies"))
        .and(bearer_token("test-jwt"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!([
            {
                "id": "company-1",
                "name": "Acme",
                "primary": true,
                "agents": [
                    { "id": "agent-1", "name": "XT", "default": true, "status": true }
                ]
            },
            {
                "id": "company-2",
                "name": "Other",
                "primary": false,
                "agents": []
            }
        ])))
        .mount(&server)
        .await;

    let companies = api::list_companies(&server.uri(), "test-jwt")
        .await
        .unwrap();
    assert_eq!(companies.len(), 2);
    assert_eq!(companies[0].id, "company-1");
    assert_eq!(companies[0].name, "Acme");
    assert!(companies[0].primary);
    assert_eq!(companies[0].agents.len(), 1);
    assert_eq!(companies[0].agents[0].name, "XT");
    assert!(companies[0].agents[0].default);
}

#[tokio::test]
async fn list_companies_parses_object_envelope() {
    let server = MockServer::start().await;

    Mock::given(method("GET"))
        .and(path("/v1/companies"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "companies": [
                { "id": "c", "name": "OnlyCo", "primary": true, "agents": [] }
            ]
        })))
        .mount(&server)
        .await;

    let companies = api::list_companies(&server.uri(), "j").await.unwrap();
    assert_eq!(companies.len(), 1);
    assert_eq!(companies[0].name, "OnlyCo");
}

#[tokio::test]
async fn list_companies_propagates_http_error() {
    let server = MockServer::start().await;

    Mock::given(method("GET"))
        .and(path("/v1/companies"))
        .respond_with(ResponseTemplate::new(401).set_body_string("unauthorized"))
        .mount(&server)
        .await;

    let err = api::list_companies(&server.uri(), "bad").await.unwrap_err();
    let msg = format!("{err:#}");
    assert!(msg.contains("401"), "expected 401 in error: {msg}");
}

#[tokio::test]
async fn list_agents_parses_array_with_default_agent_marker() {
    let server = MockServer::start().await;

    Mock::given(method("GET"))
        .and(path("/v1/agent"))
        .and(bearer_token("test-jwt"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "agents": [
                { "id": "a1", "name": "XT", "default": true, "status": true },
                { "id": "a2", "name": "Helper", "default": false, "status": true }
            ]
        })))
        .mount(&server)
        .await;

    let agents = api::list_agents(&server.uri(), "test-jwt").await.unwrap();
    assert_eq!(agents.len(), 2);
    assert!(agents[0].default);
    assert!(!agents[1].default);
}

#[tokio::test]
async fn list_agents_parses_object_keyed_by_name() {
    // Some AGiXT versions return `{"agents": {"NameA": {...}, "NameB": {...}}}`
    // — the name is the map key. We backfill it into the value.
    let server = MockServer::start().await;

    Mock::given(method("GET"))
        .and(path("/v1/agent"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "agents": {
                "XT": { "id": "id-xt", "status": true },
                "Helper": { "id": "id-helper", "status": false }
            }
        })))
        .mount(&server)
        .await;

    let mut agents = api::list_agents(&server.uri(), "j").await.unwrap();
    agents.sort_by(|a, b| a.name.cmp(&b.name));
    assert_eq!(agents.len(), 2);
    assert_eq!(agents[0].name, "Helper");
    assert_eq!(agents[1].name, "XT");
    assert_eq!(agents[1].id, "id-xt");
}

#[tokio::test]
async fn new_conversation_posts_expected_body_and_returns_id() {
    use wiremock::matchers::body_partial_json;

    let server = MockServer::start().await;

    Mock::given(method("POST"))
        .and(path("/v1/conversation"))
        .and(bearer_token("jwt"))
        .and(body_partial_json(json!({
            "agent_name": "XT",
            "conversation_name": "desktop-2026"
        })))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "id": "convo-uuid",
            "conversation_history": []
        })))
        .mount(&server)
        .await;

    let resp = api::new_conversation(&server.uri(), "jwt", "XT", "desktop-2026")
        .await
        .unwrap();
    assert_eq!(resp.id, "convo-uuid");
    assert!(resp.conversation_history.is_empty());
}

#[tokio::test]
async fn new_agent_dm_conversation_posts_group_dm_payload() {
    use wiremock::matchers::body_partial_json;

    let server = MockServer::start().await;

    Mock::given(method("POST"))
        .and(path("/v1/conversation/group"))
        .and(bearer_token("jwt"))
        .and(body_partial_json(json!({
            "conversation_name": "XT - May 6, 8:42 PM",
            "company_id": "company-uuid",
            "conversation_type": "dm",
            "agent_names": ["XT"],
            "force_new": true
        })))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "id": "dm-uuid",
            "name": "XT - May 6, 8:42 PM",
            "conversation_type": "dm"
        })))
        .mount(&server)
        .await;

    let resp = api::new_agent_dm_conversation(
        &server.uri(),
        "jwt",
        "XT",
        "company-uuid",
        "XT - May 6, 8:42 PM",
        true,
    )
    .await
    .unwrap();
    assert_eq!(resp.id, "dm-uuid");
    assert_eq!(resp.name.as_deref(), Some("XT - May 6, 8:42 PM"));
    assert_eq!(resp.agent_name.as_deref(), Some("XT"));
    assert_eq!(resp.conversation_type.as_deref(), Some("dm"));
}

#[tokio::test]
async fn list_conversations_preserves_agent_dm_metadata() {
    let server = MockServer::start().await;

    Mock::given(method("GET"))
        .and(path("/v1/conversations"))
        .and(bearer_token("jwt"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "conversations": {
                "conv-xt": {
                    "name": "XT",
                    "display_name": "XT",
                    "agent_name": "XT",
                    "conversation_type": "dm",
                    "updated_at": "2026-05-06T20:00:00Z",
                    "message_count": 2
                },
                "conv-helper": {
                    "name": "Helper chat",
                    "display_name": "Helper chat",
                    "agent_name": "Helper",
                    "conversation_type": "private",
                    "updated_at": "2026-05-06T21:00:00Z"
                }
            }
        })))
        .mount(&server)
        .await;

    let conversations = api::list_conversations(&server.uri(), "jwt").await.unwrap();
    assert_eq!(conversations.len(), 2);
    assert_eq!(conversations[0].id, "conv-helper");
    let xt = conversations.iter().find(|c| c.id == "conv-xt").unwrap();
    assert_eq!(xt.name, "XT");
    assert_eq!(xt.display_name.as_deref(), Some("XT"));
    assert_eq!(xt.agent_name.as_deref(), Some("XT"));
    assert_eq!(xt.conversation_type.as_deref(), Some("dm"));
    assert_eq!(xt.message_count, Some(2));
}

#[tokio::test]
async fn prompt_agent_sends_correct_payload_and_parses_response() {
    use wiremock::matchers::body_partial_json;

    let server = MockServer::start().await;

    Mock::given(method("POST"))
        .and(path("/v1/agent/agent-uuid/prompt"))
        .and(bearer_token("jwt"))
        .and(body_partial_json(json!({
            "prompt_name": "Think About It",
            "prompt_args": {
                "user_input": "hello",
                "conversation_name": "convo",
                "tts": true
            }
        })))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "response": "world"
        })))
        .mount(&server)
        .await;

    let resp = api::prompt_agent(
        &server.uri(),
        "jwt",
        "agent-uuid",
        "convo",
        "hello",
        true,
        None,
        Vec::new(),
    )
    .await
    .unwrap();
    assert_eq!(resp.response, "world");
}

#[tokio::test]
async fn prompt_agent_passes_context_when_provided() {
    use wiremock::matchers::body_partial_json;

    let server = MockServer::start().await;

    Mock::given(method("POST"))
        .and(path("/v1/agent/x/prompt"))
        .and(body_partial_json(json!({
            "prompt_args": {
                "user_input": "hi",
                "context": "you have desktop tools"
            }
        })))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({"response":"ok"})))
        .mount(&server)
        .await;

    let resp = api::prompt_agent(
        &server.uri(),
        "j",
        "x",
        "c",
        "hi",
        false,
        Some("you have desktop tools"),
        Vec::new(),
    )
    .await
    .unwrap();
    assert_eq!(resp.response, "ok");
}

#[tokio::test]
async fn agent_vision_posts_images_and_parses_response() {
    use wiremock::matchers::body_partial_json;

    let server = MockServer::start().await;

    Mock::given(method("POST"))
        .and(path("/v1/agent/agent-uuid/vision"))
        .and(bearer_token("jwt"))
        .and(body_partial_json(json!({
            "prompt": "Action?",
            "images": ["data:image/jpeg;base64,AAAA"],
            "use_smartest": false
        })))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "response": "Action: click(25, 320)"
        })))
        .mount(&server)
        .await;

    let images = vec!["data:image/jpeg;base64,AAAA".to_string()];
    let resp = api::agent_vision(
        &server.uri(),
        "jwt",
        "agent-uuid",
        "Action?",
        &images,
        false,
    )
    .await
    .unwrap();
    assert_eq!(resp.response, "Action: click(25, 320)");
}

#[tokio::test]
async fn list_oauth_providers_filters_to_login_capable_caller_side() {
    // The helper itself returns *all* providers; the IPC layer is what
    // filters to login_capable. So this just asserts shape parsing.
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/v1/oauth"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "providers": [
                {"name": "google", "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
                 "client_id": "g.apps", "scopes": "openid email",
                 "pkce_required": true, "login_capable": true},
                {"name": "microsoft_calendar", "authorize": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
                 "client_id": "ms-cal", "scopes": "Calendars.Read",
                 "pkce_required": false, "login_capable": false}
            ]
        })))
        .mount(&server)
        .await;

    let providers = api::list_oauth_providers(&server.uri()).await.unwrap();
    assert_eq!(providers.len(), 2);
    assert_eq!(providers[0].name, "google");
    assert!(providers[0].login_capable);
    assert!(!providers[1].login_capable);
}

#[tokio::test]
async fn login_password_returns_token_on_success() {
    use wiremock::matchers::body_partial_json;
    let server = MockServer::start().await;
    Mock::given(method("POST"))
        .and(path("/v1/login"))
        .and(body_partial_json(json!({
            "username": "u@example.com",
            "password": "pass"
        })))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "token": "eyJabc.def.ghi",
            "email": "u@example.com",
            "detail": "?token=eyJabc.def.ghi"
        })))
        .mount(&server)
        .await;

    let resp = api::login_password(&server.uri(), "u@example.com", "pass", None)
        .await
        .unwrap();
    assert_eq!(resp.token.as_deref(), Some("eyJabc.def.ghi"));
    assert_eq!(resp.email.as_deref(), Some("u@example.com"));
}

#[tokio::test]
async fn login_password_surfaces_mfa_required_softly() {
    let server = MockServer::start().await;
    Mock::given(method("POST"))
        .and(path("/v1/login"))
        .respond_with(ResponseTemplate::new(400).set_body_json(json!({
            "mfa_required": true,
            "detail": "MFA required"
        })))
        .mount(&server)
        .await;

    let resp = api::login_password(&server.uri(), "u@example.com", "pass", None)
        .await
        .unwrap();
    assert_eq!(resp.mfa_required, Some(true));
    assert!(resp.token.is_none());
}

#[tokio::test]
async fn login_password_passes_mfa_token_when_provided() {
    use wiremock::matchers::body_partial_json;
    let server = MockServer::start().await;
    Mock::given(method("POST"))
        .and(path("/v1/login"))
        .and(body_partial_json(json!({
            "username": "u@example.com", "password": "p", "mfa_token": "123456"
        })))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({"token":"jwt"})))
        .mount(&server)
        .await;

    let resp = api::login_password(&server.uri(), "u@example.com", "p", Some("123456"))
        .await
        .unwrap();
    assert_eq!(resp.token.as_deref(), Some("jwt"));
}

#[tokio::test]
async fn login_password_preserves_payment_required_context() {
    let server = MockServer::start().await;
    Mock::given(method("POST"))
        .and(path("/v1/login"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "detail": "Login successful",
            "token": "limited-jwt",
            "email": "trial@example.com",
            "payment_required": true,
            "pricing_model": "tiered_plan",
            "company_id": "company-needs-payment",
            "user_id": "user-uuid",
            "username": "trial"
        })))
        .mount(&server)
        .await;

    let resp = api::login_password(&server.uri(), "trial@example.com", "pass", None)
        .await
        .unwrap();
    assert_eq!(resp.token.as_deref(), Some("limited-jwt"));
    assert_eq!(resp.payment_required, Some(true));
    assert_eq!(resp.pricing_model.as_deref(), Some("tiered_plan"));
    assert_eq!(resp.company_id.as_deref(), Some("company-needs-payment"));
    assert_eq!(resp.user_id.as_deref(), Some("user-uuid"));
    assert_eq!(resp.username.as_deref(), Some("trial"));
}

#[tokio::test]
async fn request_magic_link_posts_email() {
    use wiremock::matchers::body_partial_json;
    let server = MockServer::start().await;
    Mock::given(method("POST"))
        .and(path("/v1/login/request-link"))
        .and(body_partial_json(json!({"email": "u@example.com"})))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({"detail": "sent"})))
        .mount(&server)
        .await;

    api::request_magic_link(&server.uri(), "u@example.com")
        .await
        .unwrap();
}

#[tokio::test]
async fn register_user_returns_token() {
    use wiremock::matchers::body_partial_json;
    let server = MockServer::start().await;
    Mock::given(method("POST"))
        .and(path("/v1/user"))
        .and(body_partial_json(json!({
            "email": "new@example.com",
            "first_name": "New",
            "last_name": "User",
            "password": "Secret1!",
            "confirm_password": "Secret1!"
        })))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "token": "jwt-token",
            "magic_link": "https://app/x?token=jwt-token",
            "otp_uri": "otpauth://totp/x"
        })))
        .mount(&server)
        .await;

    let resp = api::register_user(
        &server.uri(),
        "new@example.com",
        "New",
        "User",
        "Secret1!",
        None,
    )
    .await
    .unwrap();
    assert_eq!(resp.token.as_deref(), Some("jwt-token"));
    assert!(resp.otp_uri.is_some());
}

#[tokio::test]
async fn get_conversation_history_returns_flat_message_list() {
    use wiremock::matchers::{bearer_token, query_param};

    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/v1/conversation/conv-1"))
        .and(bearer_token("jwt"))
        .and(query_param("limit", "200"))
        .and(query_param("page", "1"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "conversation_history": [
                {"id": "m1", "role": "user", "message": "hi", "timestamp": "2026-05-04T17:00:00Z"},
                {"id": "m2", "role": "assistant", "message": "hello", "timestamp": "2026-05-04T17:00:01Z"}
            ],
            "total": 2
        })))
        .mount(&server)
        .await;

    let entries = api::get_conversation_history(&server.uri(), "jwt", "conv-1", 200, 1)
        .await
        .unwrap();
    assert_eq!(entries.len(), 2);
    assert_eq!(entries[0]["role"].as_str(), Some("user"));
    assert_eq!(entries[1]["message"].as_str(), Some("hello"));
}

#[tokio::test]
async fn workspace_upload_uses_files_array_and_destination_path() {
    use wiremock::matchers::{body_string_contains, header_exists};
    let server = MockServer::start().await;

    Mock::given(method("POST"))
        .and(path("/v1/conversation/c-1/workspace/upload"))
        .and(header_exists("authorization"))
        // multipart/form-data: parts include files and destination_path
        .and(body_string_contains("name=\"files\""))
        .and(body_string_contains("name=\"destination_path\""))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "path": "/",
            "items": [{ "name": "code.py", "type": "file", "size": 5 }]
        })))
        .mount(&server)
        .await;

    let resp = api::workspace_upload(
        &server.uri(),
        "j",
        "c-1",
        "code.py",
        b"hello".to_vec(),
        Some("src/"),
    )
    .await
    .unwrap();
    assert_eq!(resp["path"], "/");
}

#[tokio::test]
async fn workspace_download_passes_path_query_param() {
    use wiremock::matchers::query_param;
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/v1/conversation/c-1/workspace/download"))
        .and(query_param("path", "src/code.py"))
        .respond_with(ResponseTemplate::new(200).set_body_bytes(&b"hello"[..]))
        .mount(&server)
        .await;

    let bytes = api::workspace_download(&server.uri(), "j", "c-1", "src/code.py")
        .await
        .unwrap();
    assert_eq!(bytes, b"hello");
}

#[tokio::test]
async fn workspace_list_handles_object_envelope() {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/v1/conversation/c-1/workspace"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "path": "/",
            "items": [
                {"name": "a.py", "type": "file", "size": 10},
                {"name": "src", "type": "directory"}
            ]
        })))
        .mount(&server)
        .await;
    let items = api::workspace_list(&server.uri(), "j", "c-1", None)
        .await
        .unwrap();
    assert_eq!(items.len(), 2);
    assert_eq!(items[0].name, "a.py");
    assert_eq!(items[1].kind, "directory");
}

#[tokio::test]
async fn prompt_agent_does_not_put_command_overrides_in_prompt_args() {
    // Regression test: AGiXT's `/v1/agent/{id}/prompt` chain crashes
    // with `XT.AGiXT.inference() got multiple values for keyword
    // argument 'command_overrides'` if `command_overrides` is in
    // `prompt_args` (see XT.py:3396-3398). We accept the argument for
    // forward-compat with /v1/chat/completions but must NOT send it
    // through the prompt_args path.
    let server = MockServer::start().await;

    Mock::given(method("POST"))
        .and(path("/v1/agent/x/prompt"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({"response":"ok"})))
        .mount(&server)
        .await;

    let overrides = vec![json!({
        "type": "function",
        "function": {
            "name": "shell_run",
            "description": "Run a command",
            "parameters": {"type": "object"}
        }
    })];

    let resp = api::prompt_agent(&server.uri(), "j", "x", "c", "hi", false, None, overrides)
        .await
        .unwrap();
    assert_eq!(resp.response, "ok");

    let received = server.received_requests().await.unwrap();
    let body = std::str::from_utf8(&received.last().unwrap().body).unwrap();
    assert!(
        !body.contains("command_overrides"),
        "prompt_args must not contain command_overrides (collides with AGiXT internal kwarg). \
         Body was: {body}"
    );
}

#[tokio::test]
async fn prompt_agent_omits_context_when_none() {
    let server = MockServer::start().await;

    Mock::given(method("POST"))
        .and(path("/v1/agent/x/prompt"))
        // Body must not contain the context key.
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({"response":"ok"})))
        .mount(&server)
        .await;

    let resp = api::prompt_agent(&server.uri(), "j", "x", "c", "hi", false, None, Vec::new())
        .await
        .unwrap();
    assert_eq!(resp.response, "ok");

    let received = server.received_requests().await.unwrap();
    let last = received.last().unwrap();
    let body_str = std::str::from_utf8(&last.body).unwrap();
    assert!(
        !body_str.contains("context"),
        "request body should omit context: {body_str}"
    );
}

#[tokio::test]
async fn prompt_agent_strips_trailing_slash_from_server_url() {
    let server = MockServer::start().await;

    Mock::given(method("POST"))
        .and(path("/v1/agent/x/prompt"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({"response":"ok"})))
        .mount(&server)
        .await;

    // Note the trailing slash on the URL.
    let url_with_slash = format!("{}/", server.uri());
    let resp = api::prompt_agent(&url_with_slash, "j", "x", "c", "u", false, None, Vec::new())
        .await
        .unwrap();
    assert_eq!(resp.response, "ok");
}
