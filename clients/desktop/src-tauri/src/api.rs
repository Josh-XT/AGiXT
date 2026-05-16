//! Minimal AGiXT REST helpers used by the Rust side.
//!
//! Most chat traffic goes directly from the webview JS to the AGiXT backend
//! over WebSocket — this module only handles auxiliary calls that are easier
//! from Rust (login probe, conversation creation), or that we want to keep
//! secrets out of the webview for.

use anyhow::{anyhow, Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentInfo {
    pub id: String,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub status: bool,
    #[serde(default)]
    pub default: bool,
    #[serde(default)]
    pub company_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompanyInfo {
    pub id: String,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub primary: bool,
    #[serde(default)]
    pub agents: Vec<AgentInfo>,
}

pub fn build_client() -> Result<reqwest::Client> {
    reqwest::Client::builder()
        .user_agent(concat!("agixt-desktop/", env!("CARGO_PKG_VERSION")))
        .timeout(std::time::Duration::from_secs(30))
        .build()
        .context("build http client")
}

pub fn build_streaming_client() -> Result<reqwest::Client> {
    reqwest::Client::builder()
        .user_agent(concat!("agixt-desktop/", env!("CARGO_PKG_VERSION")))
        .read_timeout(std::time::Duration::from_secs(300))
        .build()
        .context("build streaming http client")
}

async fn post_json_value<T: Serialize + ?Sized>(
    server_url: &str,
    jwt: &str,
    path: &str,
    body: &T,
) -> Result<Value> {
    let client = build_client()?;
    let url = format!("{}{}", server_url.trim_end_matches('/'), path);
    let resp = client
        .post(&url)
        .bearer_auth(jwt)
        .json(body)
        .send()
        .await
        .with_context(|| format!("POST {path}"))?;
    if !resp.status().is_success() {
        return Err(anyhow!(
            "{} http {}: {}",
            path,
            resp.status(),
            resp.text().await.unwrap_or_default()
        ));
    }
    Ok(resp.json().await?)
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct BiometricCompanyRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub company_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HardwareTokenVerifyStartRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub company_id: Option<String>,
    pub key_id: String,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct BiometricSample {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub data_base64: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sample: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub quality_score: Option<f32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub liveness_result: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub transcript: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub metadata: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BiometricEnrollmentVerifyRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub company_id: Option<String>,
    pub challenge_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub device_class: Option<String>,
    pub samples: Vec<BiometricSample>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub metadata: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IdentityEvidenceRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub company_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub machine_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub conversation_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub stream_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub command_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub challenge_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub nonce: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sequence_number: Option<i64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub captured_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sent_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub content_type: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub codec: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub width: Option<i32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub height: Option<i32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sample_rate_hz: Option<i32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub channels: Option<i32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub duration_ms: Option<i32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub payload_sha256: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub previous_payload_sha256: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub key_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub signature: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub transport_format: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub evidence_profile: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub action_type: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub command_name: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub dropped_media_count: Option<i32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub drop_reason: Option<String>,
    pub method_type: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub data_base64: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sample: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub liveness_result: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub pad_result: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub iad_result: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sensor_attestation_result: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub device_integrity_result: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub media_forensics_result: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub quality_score: Option<f32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub device_class: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub risk_level: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub required_assurance: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub metadata: Option<Value>,
}

pub async fn biometric_face_enroll_start(
    server_url: &str,
    jwt: &str,
    company_id: Option<String>,
) -> Result<Value> {
    post_json_value(
        server_url,
        jwt,
        "/v1/user/mfa/face/enroll/start",
        &BiometricCompanyRequest { company_id },
    )
    .await
}

pub async fn biometric_face_enroll_verify(
    server_url: &str,
    jwt: &str,
    request: &BiometricEnrollmentVerifyRequest,
) -> Result<Value> {
    post_json_value(server_url, jwt, "/v1/user/mfa/face/enroll/verify", request).await
}

pub async fn biometric_voice_enroll_start(
    server_url: &str,
    jwt: &str,
    company_id: Option<String>,
) -> Result<Value> {
    post_json_value(
        server_url,
        jwt,
        "/v1/user/mfa/voice/enroll/start",
        &BiometricCompanyRequest { company_id },
    )
    .await
}

pub async fn biometric_voice_enroll_verify(
    server_url: &str,
    jwt: &str,
    request: &BiometricEnrollmentVerifyRequest,
) -> Result<Value> {
    post_json_value(server_url, jwt, "/v1/user/mfa/voice/enroll/verify", request).await
}

pub async fn biometric_submit_evidence(
    server_url: &str,
    jwt: &str,
    request: &IdentityEvidenceRequest,
) -> Result<Value> {
    post_json_value(server_url, jwt, "/v1/identity/evidence", request).await
}

pub async fn webauthn_register_start(
    server_url: &str,
    jwt: &str,
    request: &BiometricCompanyRequest,
) -> Result<Value> {
    post_json_value(
        server_url,
        jwt,
        "/v1/user/mfa/webauthn/register/start",
        request,
    )
    .await
}

pub async fn webauthn_register_finish(
    server_url: &str,
    jwt: &str,
    request: &Value,
) -> Result<Value> {
    post_json_value(
        server_url,
        jwt,
        "/v1/user/mfa/webauthn/register/finish",
        request,
    )
    .await
}

pub async fn webauthn_authenticate_start(
    server_url: &str,
    jwt: &str,
    request: &BiometricCompanyRequest,
) -> Result<Value> {
    post_json_value(
        server_url,
        jwt,
        "/v1/user/mfa/webauthn/authenticate/start",
        request,
    )
    .await
}

pub async fn webauthn_authenticate_finish(
    server_url: &str,
    jwt: &str,
    request: &Value,
) -> Result<Value> {
    post_json_value(
        server_url,
        jwt,
        "/v1/user/mfa/webauthn/authenticate/finish",
        request,
    )
    .await
}

pub async fn hardware_token_register_start(
    server_url: &str,
    jwt: &str,
    request: &BiometricCompanyRequest,
) -> Result<Value> {
    post_json_value(
        server_url,
        jwt,
        "/v1/user/mfa/hardware-token/register/start",
        request,
    )
    .await
}

pub async fn hardware_token_register_finish(
    server_url: &str,
    jwt: &str,
    request: &Value,
) -> Result<Value> {
    post_json_value(
        server_url,
        jwt,
        "/v1/user/mfa/hardware-token/register/finish",
        request,
    )
    .await
}

pub async fn hardware_token_verify_start(
    server_url: &str,
    jwt: &str,
    request: &HardwareTokenVerifyStartRequest,
) -> Result<Value> {
    post_json_value(
        server_url,
        jwt,
        "/v1/user/mfa/hardware-token/verify/start",
        request,
    )
    .await
}

pub async fn hardware_token_verify(server_url: &str, jwt: &str, request: &Value) -> Result<Value> {
    post_json_value(
        server_url,
        jwt,
        "/v1/user/mfa/hardware-token/verify",
        request,
    )
    .await
}

pub async fn list_companies(server_url: &str, jwt: &str) -> Result<Vec<CompanyInfo>> {
    let client = build_client()?;
    let url = format!("{}/v1/companies", server_url.trim_end_matches('/'));
    let resp = client
        .get(&url)
        .bearer_auth(jwt)
        .send()
        .await
        .context("GET /v1/companies")?;
    if !resp.status().is_success() {
        return Err(anyhow!(
            "companies http {}: {}",
            resp.status(),
            resp.text().await.unwrap_or_default()
        ));
    }
    let body: serde_json::Value = resp.json().await?;
    // Backend returns either a bare list or { companies: [...] }
    let arr = match body {
        serde_json::Value::Array(a) => a,
        serde_json::Value::Object(mut o) => o
            .remove("companies")
            .and_then(|v| {
                if let serde_json::Value::Array(a) = v {
                    Some(a)
                } else {
                    None
                }
            })
            .ok_or_else(|| anyhow!("unexpected companies response shape"))?,
        other => return Err(anyhow!("unexpected companies response: {other}")),
    };
    Ok(arr
        .into_iter()
        .filter_map(|v| serde_json::from_value(v).ok())
        .collect())
}

pub async fn list_agents(server_url: &str, jwt: &str) -> Result<Vec<AgentInfo>> {
    let client = build_client()?;
    let url = format!("{}/v1/agent", server_url.trim_end_matches('/'));
    let resp = client
        .get(&url)
        .bearer_auth(jwt)
        .send()
        .await
        .context("GET /v1/agent")?;
    if !resp.status().is_success() {
        return Err(anyhow!(
            "agents http {}: {}",
            resp.status(),
            resp.text().await.unwrap_or_default()
        ));
    }
    let body: serde_json::Value = resp.json().await?;
    let arr = match body {
        serde_json::Value::Array(a) => a,
        serde_json::Value::Object(mut o) => o
            .remove("agents")
            .map(|v| match v {
                serde_json::Value::Array(a) => a,
                serde_json::Value::Object(map) => map
                    .into_iter()
                    .map(|(k, mut v)| {
                        if let serde_json::Value::Object(ref mut obj) = v {
                            obj.entry("name".to_string())
                                .or_insert(serde_json::Value::String(k.clone()));
                        }
                        v
                    })
                    .collect(),
                _ => Vec::new(),
            })
            .ok_or_else(|| anyhow!("unexpected agents response shape"))?,
        other => return Err(anyhow!("unexpected agents response: {other}")),
    };
    Ok(arr
        .into_iter()
        .filter_map(|v| serde_json::from_value(v).ok())
        .collect())
}

#[derive(Debug, Serialize)]
struct NewConversationRequest<'a> {
    agent_name: &'a str,
    conversation_name: &'a str,
    conversation_content: Vec<serde_json::Value>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct NewConversationResponse {
    pub id: String,
    #[serde(default)]
    pub conversation_history: Vec<serde_json::Value>,
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default)]
    pub display_name: Option<String>,
    #[serde(default)]
    pub agent_name: Option<String>,
    #[serde(default)]
    pub conversation_type: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConversationSummary {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub display_name: Option<String>,
    #[serde(default)]
    pub agent_name: Option<String>,
    #[serde(default)]
    pub conversation_type: Option<String>,
    #[serde(default)]
    pub parent_id: Option<String>,
    #[serde(default)]
    pub updated_at: Option<String>,
    #[serde(default)]
    pub message_count: Option<u64>,
}

/// Fetch the full message history for a conversation. Each entry has
/// the same shape as the WebSocket `message_added` event payload —
/// `{ id, role, message, timestamp }` — so the chat renderer can use
/// the same `ingest()` path it already uses for live messages.
pub async fn get_conversation_history(
    server_url: &str,
    jwt: &str,
    conversation_id: &str,
    limit: u32,
    page: u32,
) -> Result<Vec<serde_json::Value>> {
    let client = build_client()?;
    let url = format!(
        "{}/v1/conversation/{}?limit={}&page={}",
        server_url.trim_end_matches('/'),
        conversation_id,
        limit,
        page,
    );
    let resp = client.get(&url).bearer_auth(jwt).send().await?;
    if !resp.status().is_success() {
        return Err(anyhow!(
            "get_conversation_history http {}: {}",
            resp.status(),
            resp.text().await.unwrap_or_default()
        ));
    }
    let body: serde_json::Value = resp.json().await?;
    let arr = body
        .get("conversation_history")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    Ok(arr)
}

pub async fn list_conversations(server_url: &str, jwt: &str) -> Result<Vec<ConversationSummary>> {
    let client = build_client()?;
    let url = format!(
        "{}/v1/conversations?limit=500&include_counts=false",
        server_url.trim_end_matches('/')
    );
    let resp = client.get(&url).bearer_auth(jwt).send().await?;
    if !resp.status().is_success() {
        return Err(anyhow!(
            "list_conversations http {}: {}",
            resp.status(),
            resp.text().await.unwrap_or_default()
        ));
    }
    let body: serde_json::Value = resp.json().await?;
    // /v1/conversations returns:
    //   { "conversations": { "<uuid>": { "name", "display_name",
    //                                      "agent_name", "summary",
    //                                      "updated_at", ... } } }
    // The KEY is the UUID. The display name lives inside the value
    // under `display_name` (preferred) or `name` (older shape). When
    // the conversation is brand new and the chain hasn't auto-named
    // it yet, both fields are the literal "-".
    let mut out = Vec::new();
    if let Some(obj) = body.get("conversations").and_then(|c| c.as_object()) {
        for (id, details) in obj.iter() {
            let raw_name = details
                .get("display_name")
                .and_then(|v| v.as_str())
                .or_else(|| details.get("name").and_then(|v| v.as_str()))
                .unwrap_or("-")
                .to_string();
            let updated_at = details
                .get("updated_at")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string());
            let message_count = details.get("message_count").and_then(|v| v.as_u64());
            let display_name = details
                .get("display_name")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string());
            let agent_name = details
                .get("agent_name")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string());
            let conversation_type = details
                .get("conversation_type")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string());
            let parent_id = details
                .get("parent_id")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string());
            out.push(ConversationSummary {
                id: id.clone(),
                name: raw_name,
                display_name,
                agent_name,
                conversation_type,
                parent_id,
                updated_at,
                message_count,
            });
        }
    }
    // Sort newest-first by updated_at, alphabetical fallback. Use
    // descending order so the most recent conversation is on top.
    out.sort_by(|a, b| match (&b.updated_at, &a.updated_at) {
        (Some(x), Some(y)) => x.cmp(y),
        (Some(_), None) => std::cmp::Ordering::Less,
        (None, Some(_)) => std::cmp::Ordering::Greater,
        (None, None) => a.name.cmp(&b.name),
    });
    Ok(out)
}

#[derive(Debug, Serialize)]
struct GroupConversationRequest<'a> {
    conversation_name: &'a str,
    company_id: &'a str,
    conversation_type: &'static str,
    agent_names: Vec<&'a str>,
    force_new: bool,
}

/// Create or reuse the agent DM conversation shape used by the web app.
///
/// For `force_new=false`, AGiXT de-duplicates by the agent participant and
/// returns the existing DM. For `force_new=true`, the backend always creates a
/// fresh DM, so the desktop `+` button can start another conversation with the
/// same agent.
pub async fn new_agent_dm_conversation(
    server_url: &str,
    jwt: &str,
    agent_name: &str,
    company_id: &str,
    name: &str,
    force_new: bool,
) -> Result<NewConversationResponse> {
    let client = build_client()?;
    let url = format!("{}/v1/conversation/group", server_url.trim_end_matches('/'));
    let body = GroupConversationRequest {
        conversation_name: name,
        company_id,
        conversation_type: "dm",
        agent_names: vec![agent_name],
        force_new,
    };
    let resp = client
        .post(&url)
        .bearer_auth(jwt)
        .json(&body)
        .send()
        .await
        .context("POST /v1/conversation/group")?;
    if !resp.status().is_success() {
        return Err(anyhow!(
            "new_agent_dm_conversation http {}: {}",
            resp.status(),
            resp.text().await.unwrap_or_default()
        ));
    }
    let mut body: NewConversationResponse = resp.json().await?;
    if body.name.is_none() {
        body.name = Some(name.to_string());
    }
    body.agent_name = body.agent_name.or_else(|| Some(agent_name.to_string()));
    body.conversation_type = body.conversation_type.or_else(|| Some("dm".to_string()));
    Ok(body)
}

/// `"-"` is AGiXT's sentinel for "this conversation hasn't been named
/// yet". The web client substitutes a friendly placeholder until the
/// chain renames it after the first exchange. Mirror that here so the
/// desktop client doesn't show a bare dash.
pub fn pretty_conversation_name(raw: &str) -> &str {
    let trimmed = raw.trim();
    if trimmed.is_empty() || trimmed == "-" {
        "New conversation"
    } else {
        raw
    }
}

pub async fn new_conversation(
    server_url: &str,
    jwt: &str,
    agent_name: &str,
    name: &str,
) -> Result<NewConversationResponse> {
    let client = build_client()?;
    let url = format!("{}/v1/conversation", server_url.trim_end_matches('/'));
    let body = NewConversationRequest {
        agent_name,
        conversation_name: name,
        conversation_content: Vec::new(),
    };
    let resp = client
        .post(&url)
        .bearer_auth(jwt)
        .json(&body)
        .send()
        .await
        .context("POST /v1/conversation")?;
    if !resp.status().is_success() {
        return Err(anyhow!(
            "new_conversation http {}: {}",
            resp.status(),
            resp.text().await.unwrap_or_default()
        ));
    }
    Ok(resp.json().await?)
}

#[derive(Debug, Serialize)]
struct PromptArgs {
    user_input: String,
    conversation_name: String,
    log_user_input: bool,
    log_output: bool,
    tts: bool,
    websearch: bool,
    analyze_user_input: bool,
    browse_links: bool,
    disable_commands: bool,
    /// Extra context injected into the system prompt server-side. AGiXT
    /// reads this exactly as written and concatenates it with its
    /// "think_deep" instructions before the model sees the prompt
    /// (see `AGiXT/agixt/endpoints/Agent.py:209-212`). We use it to
    /// announce the desktop client's local tools to the model.
    #[serde(skip_serializing_if = "Option::is_none")]
    context: Option<String>,
    // NOTE: do NOT add `command_overrides` here. AGiXT's
    // `/v1/agent/{id}/prompt` path collides on that kwarg —
    // `XT.AGiXT.inference(command_overrides=X, **prompt_args)` raises
    // "got multiple values for keyword argument 'command_overrides'"
    // when `prompt_args` also contains it (see XT.py:3396-3398).
    //
    // Native tool registration only works via /v1/chat/completions
    // (which accepts a top-level `tools` field), and that endpoint
    // bypasses Think About It. For the prompt_agent path we rely on
    // the system-prompt `context` to teach the model the tool list
    // and on `chat.js`'s fenced ```client_tool``` parser to dispatch
    // calls when the model emits them.
}

#[derive(Debug, Serialize)]
struct PromptRequest {
    prompt_name: String,
    prompt_args: PromptArgs,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct PromptResponse {
    #[serde(default)]
    pub response: String,
}

#[derive(Debug, Serialize)]
struct VisionRequest<'a> {
    prompt: &'a str,
    images: &'a [String],
    use_smartest: bool,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct VisionResponse {
    #[serde(default)]
    pub response: String,
}

pub async fn agent_vision(
    server_url: &str,
    jwt: &str,
    agent_id: &str,
    prompt: &str,
    images: &[String],
    use_smartest: bool,
) -> Result<VisionResponse> {
    let client = build_streaming_client()?;
    let url = format!(
        "{}/v1/agent/{}/vision",
        server_url.trim_end_matches('/'),
        urlencode_path(agent_id)
    );
    let body = VisionRequest {
        prompt,
        images,
        use_smartest,
    };
    let resp = client
        .post(&url)
        .bearer_auth(jwt)
        .json(&body)
        .send()
        .await
        .context("POST /v1/agent/{id}/vision")?;
    if !resp.status().is_success() {
        return Err(anyhow!(
            "agent_vision http {}: {}",
            resp.status(),
            resp.text().await.unwrap_or_default()
        ));
    }
    Ok(resp.json().await?)
}

// --- Auth ----------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OAuthProvider {
    pub name: String,
    #[serde(default)]
    pub authorize: String,
    #[serde(default)]
    pub client_id: String,
    #[serde(default)]
    pub scopes: String,
    #[serde(default)]
    pub pkce_required: bool,
    #[serde(default)]
    pub login_capable: bool,
    #[serde(default)]
    pub sso_only: bool,
}

pub async fn list_oauth_providers(server_url: &str) -> Result<Vec<OAuthProvider>> {
    let client = build_client()?;
    let url = format!("{}/v1/oauth", server_url.trim_end_matches('/'));
    let resp = client.get(&url).send().await.context("GET /v1/oauth")?;
    if !resp.status().is_success() {
        return Err(anyhow!(
            "list_oauth_providers http {}: {}",
            resp.status(),
            resp.text().await.unwrap_or_default()
        ));
    }
    let body: serde_json::Value = resp.json().await?;
    let arr = match body {
        serde_json::Value::Object(mut o) => o
            .remove("providers")
            .and_then(|v| {
                if let serde_json::Value::Array(a) = v {
                    Some(a)
                } else {
                    None
                }
            })
            .unwrap_or_default(),
        serde_json::Value::Array(a) => a,
        _ => Vec::new(),
    };
    Ok(arr
        .into_iter()
        .filter_map(|v| serde_json::from_value(v).ok())
        .collect())
}

/// Dedupe a list of providers down to one entry per OAuth authorization
/// *host*. Microsoft for example registers two login-capable entries —
/// `microsoft_sso` and `teams` — that both go to login.microsoftonline.com
/// and would render as two confusing "Microsoft" buttons. We pick the
/// entry with `sso_only=true` when present (it's the canonical login
/// app), otherwise we keep whichever came first.
pub fn dedupe_login_providers(providers: Vec<OAuthProvider>) -> Vec<OAuthProvider> {
    use std::collections::HashMap;
    // Preserve the original order via a parallel Vec; HashMap holds the
    // currently-winning index for each host.
    let mut order: Vec<usize> = Vec::new();
    let mut winners: HashMap<String, usize> = HashMap::new();
    for (i, p) in providers.iter().enumerate() {
        let host = url::Url::parse(&p.authorize)
            .ok()
            .and_then(|u| u.host_str().map(|s| s.to_string()))
            .unwrap_or_else(|| p.authorize.clone());
        match winners.get(&host) {
            None => {
                winners.insert(host.clone(), i);
                order.push(i);
            }
            Some(&existing_idx) => {
                let existing = &providers[existing_idx];
                if p.sso_only && !existing.sso_only {
                    // Replace the existing winner in place.
                    if let Some(slot) = order.iter_mut().find(|s| **s == existing_idx) {
                        *slot = i;
                    }
                    winners.insert(host, i);
                }
            }
        }
    }
    let mut providers = providers;
    let mut out = Vec::with_capacity(order.len());
    for idx in order {
        // Use `swap` trick to move out by index without cloning.
        let placeholder = OAuthProvider {
            name: String::new(),
            authorize: String::new(),
            client_id: String::new(),
            scopes: String::new(),
            pkce_required: false,
            login_capable: false,
            sso_only: false,
        };
        let p = std::mem::replace(&mut providers[idx], placeholder);
        out.push(p);
    }
    out
}

#[derive(Debug, Serialize)]
struct LoginRequest<'a> {
    /// AGiXT calls this `username` even though it accepts an email; we
    /// keep the wire field name accurate.
    username: &'a str,
    #[serde(skip_serializing_if = "str::is_empty")]
    password: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    mfa_token: Option<&'a str>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct LoginResponse {
    /// Set on success. Same shape as the JWT cookie the web client uses.
    #[serde(default)]
    pub token: Option<String>,
    /// AGiXT also returns a `detail` field containing a magic-link URL on
    /// successful password login; we surface it for completeness.
    #[serde(default)]
    pub detail: Option<String>,
    /// `true` when the server requires the user to add an MFA token.
    #[serde(default)]
    pub mfa_required: Option<bool>,
    /// On registration the server returns this so the user can scan it
    /// into an authenticator app.
    #[serde(default)]
    pub otp_uri: Option<String>,
    /// Invitation registration flows for existing/reactivated users can
    /// return a magic link instead of a direct token, matching the web UI.
    #[serde(default)]
    pub magic_link: Option<String>,
    #[serde(default)]
    pub added_to_company: Option<bool>,
    #[serde(default)]
    pub reactivated: Option<bool>,
    #[serde(default)]
    pub message: Option<String>,
    /// Bare email echoed back, used to seed the MFA prompt.
    #[serde(default)]
    pub email: Option<String>,
    /// `true` when the backend issued a limited JWT so the user can reach
    /// billing while their account is still inactive.
    #[serde(default)]
    pub payment_required: Option<bool>,
    /// Pricing model to choose the right billing action after inactive login.
    #[serde(default)]
    pub pricing_model: Option<String>,
    /// Company that needs payment. Persisted so the billing tab can open even
    /// if /v1/user is restricted for inactive accounts.
    #[serde(default)]
    pub company_id: Option<String>,
    /// Flat login metadata returned by AGiXT; optional for older servers.
    #[serde(default)]
    pub user_id: Option<String>,
    #[serde(default)]
    pub username: Option<String>,
}

pub async fn login_password(
    server_url: &str,
    email: &str,
    password: &str,
    mfa_token: Option<&str>,
) -> Result<LoginResponse> {
    let client = build_client()?;
    let url = format!("{}/v1/login", server_url.trim_end_matches('/'));
    let body = LoginRequest {
        username: email,
        password,
        mfa_token,
    };
    let resp = client
        .post(&url)
        .json(&body)
        .send()
        .await
        .context("POST /v1/login")?;
    let status = resp.status();
    let text = resp.text().await.unwrap_or_default();
    if !status.is_success() {
        // 400 with mfa_required is "soft" — return it.
        if let Ok(parsed) = serde_json::from_str::<LoginResponse>(&text) {
            if parsed.mfa_required.unwrap_or(false) {
                return Ok(parsed);
            }
        }
        return Err(anyhow!("login_password http {status}: {text}"));
    }
    Ok(serde_json::from_str(&text).unwrap_or_default())
}

#[derive(Debug, Serialize)]
struct MagicLinkRequest<'a> {
    email: &'a str,
}

pub async fn request_magic_link(server_url: &str, email: &str) -> Result<()> {
    let client = build_client()?;
    let url = format!("{}/v1/login/request-link", server_url.trim_end_matches('/'),);
    let resp = client
        .post(&url)
        .json(&MagicLinkRequest { email })
        .send()
        .await
        .context("POST /v1/login/request-link")?;
    if !resp.status().is_success() {
        return Err(anyhow!(
            "request_magic_link http {}: {}",
            resp.status(),
            resp.text().await.unwrap_or_default()
        ));
    }
    Ok(())
}

#[derive(Debug, Serialize)]
struct RegisterRequest<'a> {
    email: &'a str,
    first_name: &'a str,
    last_name: &'a str,
    password: &'a str,
    confirm_password: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    invitation_id: Option<&'a str>,
}

pub async fn register_user(
    server_url: &str,
    email: &str,
    first_name: &str,
    last_name: &str,
    password: &str,
    invitation_id: Option<&str>,
) -> Result<LoginResponse> {
    let client = build_client()?;
    let url = format!("{}/v1/user", server_url.trim_end_matches('/'));
    let body = RegisterRequest {
        email,
        first_name,
        last_name,
        password,
        confirm_password: password,
        invitation_id,
    };
    let resp = client
        .post(&url)
        .json(&body)
        .send()
        .await
        .context("POST /v1/user")?;
    let status = resp.status();
    let text = resp.text().await.unwrap_or_default();
    if !status.is_success() {
        return Err(anyhow!("register_user http {status}: {text}"));
    }
    Ok(serde_json::from_str(&text).unwrap_or_default())
}

/// PKCE challenge for OAuth flows that require it. The web client fetches
/// this from `/v1/oauth2/pkce-simple` so we mirror that shape exactly.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PkceChallenge {
    #[serde(default)]
    pub state: String,
    #[serde(default)]
    pub challenge: String,
    /// Verifier is what the server stores against `state`; we don't need
    /// it client-side, but include it so we don't drop it on round-trip.
    #[serde(default)]
    pub verifier: Option<String>,
}

pub async fn pkce_challenge(server_url: &str) -> Result<PkceChallenge> {
    let client = build_client()?;
    let url = format!("{}/v1/oauth2/pkce-simple", server_url.trim_end_matches('/'),);
    let resp = client
        .get(&url)
        .send()
        .await
        .context("GET /v1/oauth2/pkce-simple")?;
    if !resp.status().is_success() {
        return Err(anyhow!(
            "pkce_challenge http {}: {}",
            resp.status(),
            resp.text().await.unwrap_or_default()
        ));
    }
    Ok(resp.json().await.unwrap_or_default())
}

/// AGiXT's web client transforms the provider name before using it as the
/// final URL segment of the OAuth redirect: it strips a trailing `_sso`
/// (so `microsoft_sso` → `microsoft`) and replaces `_`/`.`/` ` with `-`
/// (so `github_sso` → `github`, `azure.us` → `azure-us`, etc). The OAuth
/// apps are pre-registered against this transformed slug, so we MUST
/// match exactly. See web/components/auth/OAuth.tsx:188-192.
pub fn redirect_slug_for(provider_name: &str) -> String {
    let lower = provider_name.to_ascii_lowercase();
    let stripped = lower.strip_suffix("_sso").unwrap_or(&lower);
    stripped
        .replace('_', "-")
        .replace('.', "-")
        .replace(' ', "-")
}

/// Build the URL the user should visit in their browser to start an OAuth
/// login. `redirect_uri` is the callback the OAuth provider will hit after
/// the user authorizes — for desktop we point at the AGiXT web client's
/// `/user/close/{provider}` page since it already handles the code-exchange
/// and JWT-cookie set, and the user can then copy the resulting JWT back
/// into the desktop app's "paste login URL" field.
pub fn build_oauth_url(
    provider: &OAuthProvider,
    redirect_uri: &str,
    pkce: Option<&PkceChallenge>,
) -> String {
    build_oauth_url_with_state(provider, redirect_uri, pkce, None)
}

/// Variant that accepts an extra opaque `state` payload. We use this to
/// signal "this auth flow originated from the desktop client" so the
/// web close page can redirect to the `agixt://` deep link instead of
/// stranding the user in the web UI. The desktop hint piggybacks on the
/// existing OAuth `state` param when PKCE isn't already using it.
pub fn build_oauth_url_with_state(
    provider: &OAuthProvider,
    redirect_uri: &str,
    pkce: Option<&PkceChallenge>,
    extra_state: Option<&str>,
) -> String {
    let mut params: Vec<(&str, String)> = vec![
        ("client_id", provider.client_id.clone()),
        ("redirect_uri", redirect_uri.to_string()),
        ("response_type", "code".to_string()),
        ("scope", provider.scopes.clone()),
    ];
    if provider.pkce_required {
        if let Some(p) = pkce {
            // PKCE owns the state slot — include extra_state as a
            // suffix the close page can grep for.
            let state = match extra_state {
                Some(extra) => format!("{}|{}", p.state, extra),
                None => p.state.clone(),
            };
            params.push(("state", state));
            params.push(("code_challenge", p.challenge.clone()));
            params.push(("code_challenge_method", "S256".to_string()));
        }
    } else if let Some(extra) = extra_state {
        params.push(("state", extra.to_string()));
    }
    let qs = params
        .into_iter()
        .map(|(k, v)| format!("{}={}", k, urlencode(&v)))
        .collect::<Vec<_>>()
        .join("&");
    let sep = if provider.authorize.contains('?') {
        '&'
    } else {
        '?'
    };
    format!("{}{}{}", provider.authorize, sep, qs)
}

// --- Workspace bridge ----------------------------------------------------
//
// Each AGiXT conversation has a server-side workspace (files the agent can
// read/write during a session). These helpers move bytes between that
// workspace and the user's local disk so the agent can pull a file off
// the user's machine, modify it, and push the result back.

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkspaceItem {
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub path: String,
    #[serde(default, alias = "type")]
    pub kind: String,
    #[serde(default)]
    pub size: Option<u64>,
}

pub async fn workspace_list(
    server_url: &str,
    jwt: &str,
    conversation_id: &str,
    sub_path: Option<&str>,
) -> Result<Vec<WorkspaceItem>> {
    let client = build_client()?;
    let mut url = format!(
        "{}/v1/conversation/{}/workspace",
        server_url.trim_end_matches('/'),
        conversation_id
    );
    if let Some(p) = sub_path {
        url.push_str(&format!("?path={}", urlencode_path(p)));
    }
    let resp = client.get(&url).bearer_auth(jwt).send().await?;
    if !resp.status().is_success() {
        return Err(anyhow!(
            "workspace_list http {}: {}",
            resp.status(),
            resp.text().await.unwrap_or_default()
        ));
    }
    let body: serde_json::Value = resp.json().await?;
    let arr = match body {
        serde_json::Value::Array(a) => a,
        serde_json::Value::Object(mut o) => o
            .remove("items")
            .or_else(|| o.remove("files"))
            .and_then(|v| {
                if let serde_json::Value::Array(a) = v {
                    Some(a)
                } else {
                    None
                }
            })
            .unwrap_or_default(),
        _ => Vec::new(),
    };
    Ok(arr
        .into_iter()
        .filter_map(|v| serde_json::from_value(v).ok())
        .collect())
}

pub async fn workspace_download(
    server_url: &str,
    jwt: &str,
    conversation_id: &str,
    workspace_path: &str,
) -> Result<Vec<u8>> {
    let client = build_client()?;
    let url = format!(
        "{}/v1/conversation/{}/workspace/download?path={}",
        server_url.trim_end_matches('/'),
        conversation_id,
        urlencode_path(workspace_path),
    );
    let resp = client.get(&url).bearer_auth(jwt).send().await?;
    if !resp.status().is_success() {
        return Err(anyhow!(
            "workspace_download http {}: {}",
            resp.status(),
            resp.text().await.unwrap_or_default()
        ));
    }
    Ok(resp.bytes().await?.to_vec())
}

pub async fn workspace_upload(
    server_url: &str,
    jwt: &str,
    conversation_id: &str,
    file_name: &str,
    bytes: Vec<u8>,
    workspace_path: Option<&str>,
) -> Result<serde_json::Value> {
    let client = build_client()?;
    let url = format!(
        "{}/v1/conversation/{}/workspace/upload",
        server_url.trim_end_matches('/'),
        conversation_id,
    );
    let part = reqwest::multipart::Part::bytes(bytes)
        .file_name(file_name.to_string())
        .mime_str("application/octet-stream")
        .map_err(|e| anyhow!("mime: {e}"))?;
    // AGiXT's upload endpoint expects a `files` array and `destination_path`.
    let mut form = reqwest::multipart::Form::new().part("files", part);
    if let Some(p) = workspace_path {
        form = form.text("destination_path", p.to_string());
    }
    let resp = client
        .post(&url)
        .bearer_auth(jwt)
        .multipart(form)
        .send()
        .await?;
    if !resp.status().is_success() {
        return Err(anyhow!(
            "workspace_upload http {}: {}",
            resp.status(),
            resp.text().await.unwrap_or_default()
        ));
    }
    Ok(resp.json::<serde_json::Value>().await.unwrap_or_default())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn provider(name: &str, pkce: bool) -> OAuthProvider {
        OAuthProvider {
            name: name.into(),
            authorize: "https://example.com/auth".into(),
            client_id: "client123".into(),
            scopes: "openid email".into(),
            pkce_required: pkce,
            login_capable: true,
            sso_only: false,
        }
    }

    #[test]
    fn redirect_slug_strips_sso_suffix_and_normalizes_separators() {
        assert_eq!(redirect_slug_for("microsoft_sso"), "microsoft");
        assert_eq!(redirect_slug_for("github_sso"), "github");
        assert_eq!(redirect_slug_for("google_sso"), "google");
        // Non-_sso providers keep their name, but separators are
        // normalized to dashes (matches web/components/auth/OAuth.tsx).
        assert_eq!(redirect_slug_for("discord"), "discord");
        assert_eq!(
            redirect_slug_for("microsoft_calendar"),
            "microsoft-calendar"
        );
        assert_eq!(redirect_slug_for("Some.Brand"), "some-brand");
        assert_eq!(redirect_slug_for("two words"), "two-words");
        // Idempotent.
        assert_eq!(
            redirect_slug_for(&redirect_slug_for("microsoft_sso")),
            "microsoft"
        );
    }

    fn p(name: &str, authorize: &str, sso_only: bool) -> OAuthProvider {
        OAuthProvider {
            name: name.into(),
            authorize: authorize.into(),
            client_id: "x".into(),
            scopes: "".into(),
            pkce_required: false,
            login_capable: true,
            sso_only,
        }
    }

    #[test]
    fn dedupe_keeps_sso_only_winner_per_host() {
        // Real-world AGiXT response: teams + microsoft_sso both
        // resolve to login.microsoftonline.com.
        let teams = p(
            "teams",
            "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
            false,
        );
        let microsoft_sso = p(
            "microsoft_sso",
            "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            true,
        );
        let github = p(
            "github_sso",
            "https://github.com/login/oauth/authorize",
            true,
        );
        let discord = p("discord", "https://discord.com/api/oauth2/authorize", false);
        let spotify = p("spotify", "https://accounts.spotify.com/authorize", false);

        let deduped = dedupe_login_providers(vec![
            teams.clone(),
            github.clone(),
            spotify.clone(),
            microsoft_sso.clone(),
            discord.clone(),
        ]);
        let names: Vec<&str> = deduped.iter().map(|p| p.name.as_str()).collect();
        // Microsoft host kept only once, with the sso_only entry.
        assert!(names.contains(&"microsoft_sso"));
        assert!(!names.contains(&"teams"));
        assert!(names.contains(&"github_sso"));
        assert!(names.contains(&"discord"));
        assert!(names.contains(&"spotify"));
        assert_eq!(deduped.len(), 4);
    }

    #[test]
    fn dedupe_preserves_first_when_no_sso_only_winner() {
        let a = p("dual_a", "https://shared.example.com/oauth", false);
        let b = p("dual_b", "https://shared.example.com/oauth", false);
        let deduped = dedupe_login_providers(vec![a.clone(), b]);
        assert_eq!(deduped.len(), 1);
        assert_eq!(deduped[0].name, "dual_a");
    }

    /// AGiXT's OAuth apps are registered against the *web client* URL,
    /// not the backend. If we send the backend URL as `redirect_uri`,
    /// every provider rejects with `redirect_uri_mismatch`. Pin that
    /// behavior with a test so we never regress.
    #[test]
    fn redirect_uri_should_be_web_not_backend() {
        let p = provider("microsoft_sso", false);
        // Caller will pass `{web_url}/user/close/{provider}` as the
        // redirect URI — confirm we forward exactly that without
        // sneaking in the backend URL anywhere.
        let redirect = "https://josh.devxt.com/user/close/microsoft_sso";
        let url = build_oauth_url(&p, redirect, None);
        let encoded = "redirect_uri=https%3A%2F%2Fjosh.devxt.com%2Fuser%2Fclose%2Fmicrosoft_sso";
        assert!(
            url.contains(encoded),
            "missing/wrong redirect_uri in: {url}"
        );
        // And the URL must NOT mention the backend host even by
        // accident.
        assert!(
            !url.contains("apijosh"),
            "backend host leaked into oauth url: {url}"
        );
        assert!(
            !url.contains("localhost%3A7437"),
            "backend host leaked: {url}"
        );
    }

    #[test]
    fn build_oauth_url_includes_required_params() {
        let p = provider("google", false);
        let url = build_oauth_url(&p, "https://app.example.com/callback", None);
        assert!(url.contains("client_id=client123"));
        assert!(url.contains("response_type=code"));
        assert!(url.contains("scope=openid%20email"));
        assert!(url.contains("redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback"));
        assert!(url.starts_with("https://example.com/auth?"));
    }

    #[test]
    fn build_oauth_url_appends_pkce_when_required() {
        let p = provider("google", true);
        let pkce = PkceChallenge {
            state: "abc".into(),
            challenge: "xyz".into(),
            verifier: None,
        };
        let url = build_oauth_url(&p, "https://app/cb", Some(&pkce));
        assert!(url.contains("state=abc"));
        assert!(url.contains("code_challenge=xyz"));
        assert!(url.contains("code_challenge_method=S256"));
    }

    #[test]
    fn build_oauth_url_uses_existing_query_separator() {
        let mut p = provider("oddball", false);
        p.authorize = "https://example.com/auth?prompt=consent".into();
        let url = build_oauth_url(&p, "https://app/cb", None);
        // Should have exactly one '?' and the new params joined with '&'.
        assert_eq!(url.matches('?').count(), 1);
        assert!(url.contains("prompt=consent&client_id=client123"));
    }

    #[test]
    fn urlencode_escapes_reserved_chars() {
        assert_eq!(urlencode("hello world"), "hello%20world");
        assert_eq!(urlencode("a/b/c"), "a%2Fb%2Fc"); // strict form-encoded
        assert_eq!(urlencode("a&b=c"), "a%26b%3Dc");
        assert_eq!(urlencode("safe-_.~"), "safe-_.~");
    }
}

fn urlencode(s: &str) -> String {
    // Strict per RFC 3986 application/x-www-form-urlencoded: only the
    // unreserved set passes through. Notably `/` is encoded so OAuth
    // redirect_uri values come out as `https%3A%2F%2F…`.
    let mut out = String::with_capacity(s.len());
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(b as char)
            }
            b' ' => out.push_str("%20"),
            _ => out.push_str(&format!("%{:02X}", b)),
        }
    }
    out
}

/// Path-preserving encoder for workspace path query params: `/` and `.`
/// pass through unchanged, but spaces and other special chars are still
/// percent-encoded. Required because AGiXT's workspace endpoints take
/// the path segment in a query param and don't double-decode it.
fn urlencode_path(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' | b'/' => {
                out.push(b as char)
            }
            b' ' => out.push_str("%20"),
            _ => out.push_str(&format!("%{:02X}", b)),
        }
    }
    out
}

pub async fn prompt_agent(
    server_url: &str,
    jwt: &str,
    agent_id: &str,
    conversation_name: &str,
    user_input: &str,
    voice: bool,
    system_prompt: Option<&str>,
    // Reserved for the future when we move to /v1/chat/completions; the
    // current /v1/agent/{id}/prompt path can't accept these without
    // colliding with an internal kwarg, so this argument is currently
    // ignored. Kept on the signature so callers don't have to change
    // when we make the switch.
    _command_overrides: Vec<serde_json::Value>,
) -> Result<PromptResponse> {
    let client = build_client()?;
    let url = format!(
        "{}/v1/agent/{}/prompt",
        server_url.trim_end_matches('/'),
        agent_id
    );
    let body = PromptRequest {
        prompt_name: "Think About It".to_string(),
        prompt_args: PromptArgs {
            user_input: user_input.to_string(),
            conversation_name: conversation_name.to_string(),
            log_user_input: true,
            log_output: true,
            tts: voice,
            websearch: false,
            analyze_user_input: false,
            browse_links: false,
            disable_commands: false,
            context: system_prompt
                .filter(|s| !s.trim().is_empty())
                .map(|s| s.to_string()),
        },
    };
    let resp = client
        .post(&url)
        .bearer_auth(jwt)
        .json(&body)
        .send()
        .await
        .context("POST /v1/agent/{id}/prompt")?;
    if !resp.status().is_success() {
        return Err(anyhow!(
            "prompt_agent http {}: {}",
            resp.status(),
            resp.text().await.unwrap_or_default()
        ));
    }
    Ok(resp.json().await?)
}
