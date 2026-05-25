//! SSE-streaming chat client for AGiXT's `/v1/chat/completions` endpoint.
//!
//! This is the path the kids app and ESP32 client use. It supports the
//! OpenAI tools round-trip natively: send `messages + tools`, the server
//! streams `delta` chunks (text), `tool_calls` (the agent wants to call
//! a client tool), and a final `done`. The desktop client executes
//! local tools and then calls the same endpoint again with matching
//! `role: tool` results so the agent continues the same tool round.
//!
//! Why we moved off `/v1/agent/{id}/prompt`: that endpoint runs the
//! "Think About It" chain server-side and crashes when `command_overrides`
//! is in `prompt_args` (see `XT.py:3396` — the kwarg collides with an
//! internal one). It also doesn't stream the assistant's text so the
//! user has to wait for the full response. `/v1/chat/completions` is
//! OpenAI-compatible, accepts a top-level `tools` array, and streams
//! token-by-token.
//!
//! Events emitted (as Tauri events on the `chat-stream` channel):
//!   * `{ kind: "delta",      data: { text } }`        — token chunk
//!   * `{ kind: "tool_call",  data: { id, name, args } }` — agent wants
//!     to call a client tool. Args is the parsed JSON object.
//!   * `{ kind: "activity",   data: { text, type } }`  — agent thinking
//!   * `{ kind: "done",       data: { text } }`        — final answer
//!   * `{ kind: "error",      data: { message } }`     — fatal error

use anyhow::{anyhow, Context, Result};
use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;

use crate::api;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct ChatMessage {
    pub role: String,
    /// Either a plain string (most cases) or an OpenAI multimodal array.
    pub content: serde_json::Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_call_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_calls: Option<Vec<ToolCall>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub log_user_input: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub log_output: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub enable_command_selection: Option<bool>,
    /// Hidden per-turn context for AGiXT. The backend folds this into
    /// prompt_args.context instead of logging it as the user's message.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub context: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCall {
    pub id: String,
    #[serde(rename = "type")]
    pub kind: String,
    pub function: ToolCallFunction,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCallFunction {
    pub name: String,
    /// JSON-encoded string per OpenAI spec.
    pub arguments: String,
}

#[derive(Debug, Serialize)]
struct ChatRequest<'a> {
    model: &'a str,
    user: &'a str,
    messages: &'a [ChatMessage],
    #[serde(skip_serializing_if = "slice_is_empty")]
    tools: &'a [Value],
    #[serde(skip_serializing_if = "Option::is_none")]
    tools_choice: Option<&'static str>,
    stream: bool,
    temperature: f32,
    #[serde(skip_serializing_if = "Option::is_none")]
    max_tokens: Option<u32>,
}

fn slice_is_empty<T>(s: &&[T]) -> bool {
    s.is_empty()
}

/// One event emitted by the streaming consumer. We funnel these through
/// a tokio channel back to a Tauri event channel that JS subscribes to.
#[derive(Debug, Clone, Serialize)]
#[serde(tag = "kind", content = "data")]
pub enum StreamEvent {
    /// Token chunk for the assistant's reply.
    #[serde(rename = "delta")]
    Delta { text: String },
    /// Agent thinking / activity text streamed alongside the response.
    /// AGiXT emits these as `object: "activity.stream"` SSE events.
    #[serde(rename = "activity")]
    Activity {
        kind: String,
        content: String,
        complete: bool,
    },
    /// Agent is calling a client-defined tool.
    #[serde(rename = "tool_call")]
    ToolCall {
        id: String,
        name: String,
        args: Value,
        /// `remote_command` is AGiXT's client-command path. The desktop
        /// client executes it locally, then continues chat/completions with
        /// a matching role:tool result.
        origin: String,
    },
    /// Final assistant message — the full text, in case the renderer
    /// wants to dedupe against accumulated deltas.
    #[serde(rename = "done")]
    Done { text: String, finish_reason: String },
    /// Fatal error.
    #[serde(rename = "error")]
    Error { message: String },
}

/// POST to `/v1/chat/completions`, parse the SSE stream, and invoke
/// `on_event` for each parsed event. The future resolves when the
/// stream ends (either after `[DONE]` or a connection close).
pub async fn stream_chat<F>(
    server_url: &str,
    jwt: &str,
    agent_name: &str,
    conversation_name: &str,
    messages: &[ChatMessage],
    tools: &[Value],
    voice: bool,
    mut on_event: F,
) -> Result<()>
where
    F: FnMut(StreamEvent),
{
    let _ = voice; // reserved for tts pipeline
    let client = api::build_streaming_client()?;
    let url = format!("{}/v1/chat/completions", server_url.trim_end_matches('/'));
    let body = ChatRequest {
        model: agent_name,
        user: conversation_name,
        messages,
        tools,
        tools_choice: if tools.is_empty() { None } else { Some("auto") },
        stream: true,
        temperature: 0.7,
        max_tokens: None,
    };

    tracing::info!(
        "stream_chat: POST {} agent={} convo={} messages={} tools={}",
        url,
        agent_name,
        conversation_name,
        messages.len(),
        tools.len(),
    );
    let resp = client
        .post(&url)
        .bearer_auth(jwt)
        .header("Accept", "text/event-stream")
        .json(&body)
        .send()
        .await
        .context("POST /v1/chat/completions")?;

    let status = resp.status();
    tracing::info!("stream_chat: response status {status}");
    if !status.is_success() {
        let text = resp.text().await.unwrap_or_default();
        tracing::warn!("stream_chat: error body: {}", text);
        on_event(StreamEvent::Error {
            message: format!("HTTP {status}: {text}"),
        });
        return Err(anyhow!("chat completions http {status}: {text}"));
    }

    // Each chunk arrives as raw bytes; SSE messages are separated by
    // double-newlines and prefixed with `data: `. Buffer across chunks
    // since one JSON event may span two reads.
    let mut stream = resp.bytes_stream();
    let mut buffer = String::new();
    // Tool calls arrive as fragments — index→partial accumulation per
    // OpenAI streaming spec — so we accumulate by `index` then flush on
    // `finish_reason: tool_calls`.
    let mut pending_tools: HashMap<usize, AccumulatingToolCall> = HashMap::new();
    let mut full_text = String::new();
    let mut finish_reason = String::new();

    while let Some(chunk) = stream.next().await {
        let chunk = match chunk {
            Ok(b) => b,
            Err(e) => {
                on_event(StreamEvent::Error {
                    message: format!("stream read: {e}"),
                });
                return Err(e.into());
            }
        };
        let s = String::from_utf8_lossy(&chunk);
        buffer.push_str(&s);

        // Process complete events (each terminated by \n\n).
        while let Some(idx) = buffer.find("\n\n") {
            let raw_event: String = buffer.drain(..=idx + 1).collect();
            let raw_event = raw_event.trim_end_matches('\n');
            // Each event body is one or more `field: value` lines.
            let mut data_payload: Option<String> = None;
            for line in raw_event.lines() {
                if let Some(rest) = line.strip_prefix("data:") {
                    let rest = rest.trim_start();
                    if data_payload.is_none() {
                        data_payload = Some(rest.to_string());
                    } else {
                        // Multi-line data: concatenate per SSE spec.
                        data_payload.as_mut().unwrap().push('\n');
                        data_payload.as_mut().unwrap().push_str(rest);
                    }
                }
                // ignore comments (": keepalive") and `event:` lines.
            }
            let Some(payload) = data_payload else {
                continue;
            };
            if payload == "[DONE]" {
                if !pending_tools.is_empty() {
                    // Flush any tools that didn't get a finish_reason.
                    flush_pending_tools(&mut pending_tools, &mut on_event);
                }
                on_event(StreamEvent::Done {
                    text: full_text.clone(),
                    finish_reason: finish_reason.clone(),
                });
                return Ok(());
            }
            let parsed: Value = match serde_json::from_str(&payload) {
                Ok(v) => v,
                Err(e) => {
                    tracing::warn!("bad SSE payload: {e}: {}", payload);
                    continue;
                }
            };
            handle_sse_event(
                &parsed,
                &mut full_text,
                &mut finish_reason,
                &mut pending_tools,
                &mut on_event,
            );
        }
    }

    // Stream ended without an explicit [DONE].
    if !pending_tools.is_empty() {
        flush_pending_tools(&mut pending_tools, &mut on_event);
    }
    on_event(StreamEvent::Done {
        text: full_text,
        finish_reason,
    });
    Ok(())
}

#[derive(Default)]
struct AccumulatingToolCall {
    id: String,
    name: String,
    arguments: String,
}

/// Dispatch one parsed SSE payload. AGiXT's stream is not pure OpenAI —
/// it interleaves four `object` types we have to recognize:
///
///   * `chat.completion.chunk` — OpenAI-shaped delta (text content,
///     finish_reason, sometimes streaming tool_calls).
///   * `activity.stream` — agent thinking / activity narration. Emitted
///     before/after the assistant's reply.
///   * `remote_command.request` — the canonical AGiXT shape for "agent
///     wants to call a client tool". Carries `tool_name`, `tool_args`
///     (already parsed JSON), and `request_id` we use as the
///     `tool_call_id` when sending the result back.
///   * `remote_command.pending` — purely informational ("we're waiting
///     for the client"), safe to ignore.
fn handle_sse_event<F: FnMut(StreamEvent)>(
    parsed: &Value,
    full_text: &mut String,
    finish_reason: &mut String,
    pending_tools: &mut HashMap<usize, AccumulatingToolCall>,
    on_event: &mut F,
) {
    let object_type = parsed.get("object").and_then(|v| v.as_str()).unwrap_or("");

    match object_type {
        "remote_command.request" => {
            let id = parsed
                .get("request_id")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let name = parsed
                .get("tool_name")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let args = parsed
                .get("tool_args")
                .cloned()
                .unwrap_or_else(|| Value::Object(Default::default()));
            on_event(StreamEvent::ToolCall {
                id,
                name,
                args,
                origin: "remote_command".to_string(),
            });
            return;
        }
        "remote_command.pending" => return,
        "activity.stream" => {
            let kind = parsed
                .get("type")
                .and_then(|v| v.as_str())
                .unwrap_or("activity")
                .to_string();
            let content = parsed
                .get("content")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let complete = parsed
                .get("complete")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            on_event(StreamEvent::Activity {
                kind,
                content,
                complete,
            });
            return;
        }
        _ => {} // fall through to OpenAI-shaped handling below
    }

    let Some(choice) = parsed
        .get("choices")
        .and_then(|c| c.as_array())
        .and_then(|c| c.first())
    else {
        return;
    };
    if let Some(fr) = choice.get("finish_reason").and_then(|v| v.as_str()) {
        *finish_reason = fr.to_string();
        if fr == "tool_calls" {
            flush_pending_tools(pending_tools, on_event);
        }
    }
    let Some(delta) = choice.get("delta") else {
        return;
    };
    if let Some(text) = delta.get("content").and_then(|v| v.as_str()) {
        if let Some(incremental_text) = normalize_full_text_delta(full_text, text) {
            on_event(StreamEvent::Delta {
                text: incremental_text,
            });
        }
    }
    if let Some(arr) = delta.get("tool_calls").and_then(|v| v.as_array()) {
        for tc in arr {
            let Some(idx) = tc.get("index").and_then(|v| v.as_u64()) else {
                continue;
            };
            let entry = pending_tools.entry(idx as usize).or_default();
            if let Some(id) = tc.get("id").and_then(|v| v.as_str()) {
                entry.id.push_str(id);
            }
            if let Some(func) = tc.get("function") {
                if let Some(name) = func.get("name").and_then(|v| v.as_str()) {
                    entry.name.push_str(name);
                }
                if let Some(args) = func.get("arguments").and_then(|v| v.as_str()) {
                    entry.arguments.push_str(args);
                }
            }
        }
    }
}

fn normalize_full_text_delta(full_text: &mut String, chunk: &str) -> Option<String> {
    if chunk.is_empty() {
        return None;
    }
    if full_text.is_empty() {
        full_text.push_str(chunk);
        return Some(chunk.to_string());
    }
    // Most OpenAI-compatible providers send token deltas, but some AGiXT/
    // WorkConductor paths can forward cumulative snapshots. Convert those
    // snapshots into the missing suffix so the webview always receives
    // append-only text.
    if chunk.starts_with(full_text.as_str()) {
        let suffix = chunk[full_text.len()..].to_string();
        full_text.clear();
        full_text.push_str(chunk);
        return if suffix.is_empty() {
            None
        } else {
            Some(suffix)
        };
    }
    if full_text.starts_with(chunk) {
        return None;
    }
    full_text.push_str(chunk);
    Some(chunk.to_string())
}

fn flush_pending_tools<F: FnMut(StreamEvent)>(
    pending: &mut HashMap<usize, AccumulatingToolCall>,
    on_event: &mut F,
) {
    // Drain in index order so the agent observes a stable ordering when
    // multiple tools are dispatched in parallel.
    let mut keys: Vec<usize> = pending.keys().copied().collect();
    keys.sort_unstable();
    for k in keys {
        if let Some(t) = pending.remove(&k) {
            let args: Value = serde_json::from_str(&t.arguments)
                .unwrap_or_else(|_| Value::String(t.arguments.clone()));
            on_event(StreamEvent::ToolCall {
                id: t.id,
                name: t.name,
                args,
                origin: "openai_tool_call".to_string(),
            });
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::cell::RefCell;

    /// Drive the parser with a sequence of SSE payloads sharing one
    /// state machine (just like a real stream would). Each element in
    /// `payloads` is the *body* after `data:` (without the `data:`
    /// prefix or the trailing blank line).
    fn parse_events(payloads: &[&str]) -> Vec<StreamEvent> {
        let collected = RefCell::new(Vec::new());
        let mut on_event = |ev: StreamEvent| collected.borrow_mut().push(ev);
        let mut pending: HashMap<usize, AccumulatingToolCall> = HashMap::new();
        let mut full_text = String::new();
        let mut finish_reason = String::new();

        for payload in payloads {
            if *payload == "[DONE]" {
                flush_pending_tools(&mut pending, &mut on_event);
                on_event(StreamEvent::Done {
                    text: full_text.clone(),
                    finish_reason: finish_reason.clone(),
                });
                continue;
            }
            let parsed: Value = match serde_json::from_str(payload) {
                Ok(v) => v,
                Err(_) => continue,
            };
            handle_sse_event(
                &parsed,
                &mut full_text,
                &mut finish_reason,
                &mut pending,
                &mut on_event,
            );
        }
        collected.into_inner()
    }

    #[test]
    fn parses_agixt_remote_command_request_as_tool_call() {
        // Real shape captured from a live AGiXT stream when the agent
        // calls `shell_run`. AGiXT does NOT use OpenAI's
        // delta.tool_calls structure — it emits a flat
        // remote_command.request with tool_name/tool_args/request_id.
        let evs = parse_events(&[
            r#"{"object":"remote_command.request","request_id":"req-123","tool_name":"shell_run","tool_args":{"command":"spotify &"}}"#,
            r#"{"object":"remote_command.pending"}"#,
            r#"{"object":"chat.completion.chunk","choices":[{"delta":{},"finish_reason":"stop"}]}"#,
            "[DONE]",
        ]);
        let tool = evs.iter().find_map(|e| match e {
            StreamEvent::ToolCall {
                id,
                name,
                args,
                origin,
            } => Some((id.clone(), name.clone(), args.clone(), origin.clone())),
            _ => None,
        });
        let (id, name, args, origin) = tool.expect("expected ToolCall, got {evs:?}");
        assert_eq!(id, "req-123");
        assert_eq!(name, "shell_run");
        assert_eq!(args["command"].as_str(), Some("spotify &"));
        assert_eq!(origin, "remote_command");
        // remote_command.pending must NOT produce an event.
        let pending_emitted = evs.iter().any(|e| match e {
            StreamEvent::ToolCall { name, .. } => name == "pending",
            _ => false,
        });
        assert!(!pending_emitted, "pending event leaked: {evs:?}");
    }

    #[test]
    fn parses_agixt_activity_stream() {
        let evs = parse_events(&[
            r#"{"object":"activity.stream","type":"thinking","content":"Analyzing request...","complete":false}"#,
            r#"{"object":"activity.stream","type":"thinking","content":"Done.","complete":true}"#,
        ]);
        let activities: Vec<_> = evs
            .iter()
            .filter_map(|e| match e {
                StreamEvent::Activity {
                    kind,
                    content,
                    complete,
                } => Some((kind.clone(), content.clone(), *complete)),
                _ => None,
            })
            .collect();
        assert_eq!(activities.len(), 2);
        assert_eq!(
            activities[0],
            ("thinking".into(), "Analyzing request...".into(), false)
        );
        assert_eq!(activities[1].2, true);
    }

    #[test]
    fn parses_text_delta() {
        let evs = parse_events(&[r#"{"choices":[{"delta":{"content":"hello"}}]}"#]);
        assert_eq!(evs.len(), 1);
        match &evs[0] {
            StreamEvent::Delta { text } => assert_eq!(text, "hello"),
            other => panic!("expected delta, got {other:?}"),
        }
    }

    #[test]
    fn normalizes_cumulative_text_snapshots() {
        let evs = parse_events(&[
            r#"{"choices":[{"delta":{"content":"hello"}}]}"#,
            r#"{"choices":[{"delta":{"content":"hello world"}}]}"#,
            r#"{"choices":[{"delta":{"content":"hello world"}}]}"#,
            "[DONE]",
        ]);
        let deltas: Vec<_> = evs
            .iter()
            .filter_map(|e| match e {
                StreamEvent::Delta { text } => Some(text.as_str()),
                _ => None,
            })
            .collect();
        assert_eq!(deltas, vec!["hello", " world"]);
        assert!(matches!(
            evs.last(),
            Some(StreamEvent::Done { text, .. }) if text == "hello world"
        ));
    }

    #[test]
    fn parses_tool_call_finish() {
        // Two events sharing parser state: (a) accumulating tool call,
        // (b) finish_reason that flushes it.
        let evs = parse_events(&[
            r#"{"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","function":{"name":"shell_run","arguments":"{\"command\":\"spotify &\"}"}}]}}]}"#,
            r#"{"choices":[{"delta":{},"finish_reason":"tool_calls"}]}"#,
        ]);
        let tool = evs.iter().find_map(|e| match e {
            StreamEvent::ToolCall {
                id,
                name,
                args,
                origin,
            } => Some((id.clone(), name.clone(), args.clone(), origin.clone())),
            _ => None,
        });
        assert!(tool.is_some(), "expected a ToolCall, got {evs:?}");
        let (id, name, args, origin) = tool.unwrap();
        assert_eq!(id, "call_1");
        assert_eq!(name, "shell_run");
        assert_eq!(args["command"].as_str(), Some("spotify &"));
        assert_eq!(origin, "openai_tool_call");
    }

    #[test]
    fn parses_streaming_tool_call_args() {
        // Real-world: arguments arrive across multiple deltas. The
        // parser must concatenate before flushing.
        let evs = parse_events(&[
            r#"{"choices":[{"delta":{"tool_calls":[{"index":0,"id":"abc","function":{"name":"shell_run","arguments":"{\"comma"}}]}}]}"#,
            r#"{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"nd\":\"echo "}}]}}]}"#,
            r#"{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"hi\"}"}}]}}]}"#,
            r#"{"choices":[{"delta":{},"finish_reason":"tool_calls"}]}"#,
        ]);
        let tool = evs.iter().find_map(|e| match e {
            StreamEvent::ToolCall {
                id,
                name,
                args,
                origin,
            } => Some((id.clone(), name.clone(), args.clone(), origin.clone())),
            _ => None,
        });
        let (id, name, args, origin) = tool.expect("tool call missing");
        assert_eq!(id, "abc");
        assert_eq!(name, "shell_run");
        assert_eq!(args["command"].as_str(), Some("echo hi"));
        assert_eq!(origin, "openai_tool_call");
    }

    #[test]
    fn done_emitted_on_done_marker() {
        let evs = parse_events(&["[DONE]"]);
        assert!(matches!(evs.last(), Some(StreamEvent::Done { .. })));
    }

    #[test]
    fn chat_request_uses_agixt_tools_choice_field() {
        let messages = [ChatMessage {
            role: "user".into(),
            content: Value::String("hi".into()),
            tool_call_id: None,
            name: None,
            tool_calls: None,
            log_user_input: None,
            log_output: None,
            enable_command_selection: None,
            context: None,
        }];
        let tools = [json!({
            "type": "function",
            "function": {
                "name": "shell_run",
                "description": "Run command",
                "parameters": {"type": "object"}
            }
        })];
        let req = ChatRequest {
            model: "XT",
            user: "convo",
            messages: &messages,
            tools: &tools,
            tools_choice: Some("auto"),
            stream: true,
            temperature: 0.7,
            max_tokens: None,
        };
        let value = serde_json::to_value(req).unwrap();
        assert_eq!(value["tools_choice"].as_str(), Some("auto"));
        assert!(value.get("tool_choice").is_none());
    }
}
