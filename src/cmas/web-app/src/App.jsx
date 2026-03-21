import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Send, Plus, Bot, Activity, X, MessageSquare,
  Pause, StopCircle, Play, Terminal, List, Filter,
  Globe, Cpu, Eye, Search, FileText, Code, Command,
  Loader2, CheckCircle, Zap, ChevronRight, ChevronLeft,
  Sparkles, Network
} from 'lucide-react';

// ─── Status config ─────────────────────────────────────────────────────────────

const STATUS_DOT = {
  working:     'bg-emerald-400 animate-pulse',
  in_progress: 'bg-emerald-400 animate-pulse',
  paused:      'bg-amber-400',
  blocked:     'bg-amber-400',
  done:        'bg-zinc-500',
  completed:   'bg-zinc-500',
  failed:      'bg-red-500',
  idle:        'bg-zinc-700',
  pending:     'bg-zinc-700',
};

const STATUS_TEXT = {
  working:     'text-emerald-400',
  in_progress: 'text-emerald-400',
  paused:      'text-amber-400',
  blocked:     'text-amber-400',
  done:        'text-zinc-500',
  completed:   'text-zinc-500',
  failed:      'text-red-400',
  idle:        'text-zinc-600',
  pending:     'text-zinc-600',
};

const ACTION_COLOR = {
  success:      'text-emerald-400',
  error:        'text-red-400',
  denied:       'text-amber-400',
  rate_limited: 'text-amber-400',
  user_message: 'text-blue-400',
  response:     'text-zinc-500',
};

// Derive a stable accent color from any agent name using its characters
function agentColor(name) {
  if (!name) return 'text-zinc-500';
  const n = name.toLowerCase();
  // Semantic matches for known role keywords
  if (n.includes('orchestrat'))  return 'text-violet-400';
  if (n.includes('research'))    return 'text-sky-400';
  if (n.includes('analyst'))     return 'text-amber-400';
  if (n.includes('writer'))      return 'text-emerald-400';
  if (n.includes('develop'))     return 'text-orange-400';
  if (n.includes('mcts') || n.includes('engine') || n.includes('brain')) return 'text-purple-400';
  // Fallback: derive a color from a hash of the name so each unique agent
  // always gets the same color without any hardcoding
  const COLORS = [
    'text-sky-400', 'text-amber-400', 'text-emerald-400', 'text-rose-400',
    'text-indigo-400', 'text-cyan-400', 'text-lime-400', 'text-pink-400',
  ];
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) & 0xFFFF;
  return COLORS[hash % COLORS.length];
}

// ─── Primitives ────────────────────────────────────────────────────────────────

function StatusDot({ status, size = 'sm' }) {
  const cls = STATUS_DOT[status] || STATUS_DOT.idle;
  return <span className={`inline-block rounded-full shrink-0 ${cls} ${size === 'sm' ? 'w-1.5 h-1.5' : 'w-2 h-2'}`} />;
}

function StatusLabel({ status }) {
  const cls = STATUS_TEXT[status] || STATUS_TEXT.idle;
  return <span className={`text-xs ${cls}`}>{status ?? 'idle'}</span>;
}

function ChannelTag({ channel }) {
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-zinc-500">
      <Globe className="w-3 h-3" />{channel || 'web'}
    </span>
  );
}

function timeAgo(ts) {
  if (!ts) return '';
  const d = Date.now() / 1000 - ts;
  if (d < 5)    return 'just now';
  if (d < 60)   return `${Math.floor(d)}s ago`;
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  return `${Math.floor(d / 3600)}h ago`;
}

function progressMeta(text, agent) {
  const t = text.toLowerCase();
  // Orchestrator-level phases
  if (t.includes('pre-screening') || t.includes('dependencies'))  return { Icon: Zap,       color: 'text-violet-400' };
  if (t.includes('mcts') || t.includes('reasoning'))              return { Icon: Sparkles,   color: 'text-violet-400' };
  if (t.includes('decomposing') || t.includes('assigning'))       return { Icon: Network,    color: 'text-violet-400' };
  if (t.includes('synthesiz'))                                     return { Icon: FileText,   color: 'text-violet-400' };
  if (t.includes('evaluating') || t.includes('metacog'))          return { Icon: CheckCircle, color: 'text-violet-400' };
  // Agent-level tool use
  if (t.includes('searching') || t.includes('search'))            return { Icon: Search,     color: agentColor(agent) };
  if (t.includes('writing') || t.includes('written'))             return { Icon: FileText,   color: agentColor(agent) };
  if (t.includes('python') || t.includes('running'))              return { Icon: Code,       color: agentColor(agent) };
  if (t.includes('deploying') || t.includes('spawning'))          return { Icon: Cpu,        color: 'text-indigo-400'  };
  if (t.includes('→'))                                             return { Icon: MessageSquare, color: agentColor(agent) };
  if (t.includes('starting'))                                      return { Icon: Loader2,   color: agentColor(agent) };
  if (t.includes('completed'))                                     return { Icon: CheckCircle, color: agentColor(agent) };
  return { Icon: Loader2, color: 'text-zinc-600' };
}

// ─── Activity line (progress inline in chat) ──────────────────────────────────

function ActivityLine({ text, agent }) {
  const { Icon, color } = progressMeta(text, agent);
  const isDone = /complet|synthes|found|written/i.test(text);
  const spinning = Icon === Loader2 && !isDone;

  return (
    <div className="flex items-start gap-2 py-0.5 max-w-2xl group">
      <div className={`shrink-0 mt-0.5 ${color}`}>
        {isDone
          ? <CheckCircle className="w-3.5 h-3.5" />
          : <Icon className={`w-3.5 h-3.5 ${spinning ? 'animate-spin' : ''}`} />}
      </div>
      <div className="flex items-baseline gap-1.5 min-w-0">
        {agent && (
          <span className={`text-[11px] font-semibold shrink-0 ${agentColor(agent)}`}>{agent}</span>
        )}
        <span className="text-xs text-zinc-500 font-mono leading-relaxed truncate">{text}</span>
      </div>
    </div>
  );
}

// ─── Right Panel ───────────────────────────────────────────────────────────────

function RightPanel({ projectAgents, projectTasks, liveProgress, isOpen, onToggle }) {
  if (!isOpen) {
    return (
      <button onClick={onToggle}
        className="w-8 flex flex-col items-center py-4 border-l border-zinc-800 text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/30 transition-colors cursor-pointer shrink-0"
        title="Open activity panel">
        <ChevronLeft className="w-3.5 h-3.5" />
      </button>
    );
  }

  const activeAgents = projectAgents.filter(a => a.status === 'working');
  const idleAgents   = projectAgents.filter(a => a.status !== 'working');
  const recentTasks  = [...projectTasks]
    .sort((a, b) => (b.updated_at || b.created_at || 0) - (a.updated_at || a.created_at || 0))
    .slice(0, 10);

  // Merge live progress with agent roster for richest data
  const liveKeys = Object.keys(liveProgress);
  const allActiveNames = [...new Set([...activeAgents.map(a => a.name), ...liveKeys])];

  return (
    <aside className="w-64 flex flex-col border-l border-zinc-800 shrink-0 overflow-hidden">
      <div className="h-12 flex items-center justify-between px-4 border-b border-zinc-800 shrink-0">
        <span className="text-xs font-medium text-zinc-400">Activity</span>
        <button onClick={onToggle}
          className="w-6 h-6 flex items-center justify-center text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800 rounded transition-all cursor-pointer">
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">

        {/* Swarm — active agents with live text */}
        <div className="px-3 pt-4 pb-2">
          <p className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider mb-2 px-1">Swarm</p>
          {allActiveNames.length === 0 && idleAgents.length === 0 ? (
            <p className="text-xs text-zinc-700 px-1">No agents deployed.</p>
          ) : (
            <div className="space-y-1">
              {/* Active / with live progress */}
              {allActiveNames.map(name => {
                const liveText = liveProgress[name];
                return (
                  <div key={name} className="rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shrink-0" />
                      <span className={`text-[11px] font-medium truncate ${agentColor(name)}`}>{name}</span>
                    </div>
                    {liveText && (
                      <p className="text-[10px] text-zinc-600 mt-1 leading-relaxed line-clamp-2 font-mono">
                        {liveText}
                      </p>
                    )}
                  </div>
                );
              })}
              {/* Idle agents */}
              {idleAgents.filter(a => !allActiveNames.includes(a.name)).map(a => (
                <div key={a.name} className="flex items-center gap-2 px-1 py-1">
                  <StatusDot status="idle" />
                  <span className="text-[11px] text-zinc-600 truncate">{a.name}</span>
                  <span className="text-[10px] text-zinc-700 ml-auto shrink-0">idle</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="mx-3 border-t border-zinc-800/60 my-2" />

        {/* Tasks — grouped by status, most recent first */}
        <div className="px-3 pb-4">
          <p className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider mb-2 px-1">Tasks</p>
          {recentTasks.length === 0 ? (
            <p className="text-xs text-zinc-700 px-1">No tasks yet.</p>
          ) : (
            <div className="space-y-1">
              {recentTasks.map(t => (
                <div key={t.id} className="px-1 py-1.5">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <StatusDot status={t.status} />
                    {t.assigned_to && (
                      <span className={`text-[10px] font-medium ${agentColor(t.assigned_to)}`}>
                        {t.assigned_to}
                      </span>
                    )}
                    <span className="text-[10px] text-zinc-700 ml-auto font-mono shrink-0">{timeAgo(t.updated_at || t.created_at)}</span>
                  </div>
                  <p className="text-[10px] text-zinc-500 leading-relaxed line-clamp-2 pl-3">
                    {t.description}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
    </aside>
  );
}

// ─── Inject Bar (interject into running swarm) ─────────────────────────────────

function InjectBar({ onSteer }) {
  const [open, setOpen]   = useState(false);
  const [text, setText]   = useState('');
  const inputRef          = useRef(null);

  useEffect(() => { if (open) inputRef.current?.focus(); }, [open]);

  const submit = () => {
    if (!text.trim()) return;
    onSteer(text.trim());
    setText('');
    setOpen(false);
  };

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg border border-dashed border-zinc-700 text-zinc-600 hover:text-zinc-400 hover:border-zinc-500 transition-colors cursor-pointer text-xs">
        <Zap className="w-3.5 h-3.5" />
        Interject — inject guidance into the running swarm
      </button>
    );
  }

  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-amber-500/30 bg-amber-500/5">
      <Zap className="w-3.5 h-3.5 text-amber-400 shrink-0" />
      <input
        ref={inputRef}
        value={text}
        onChange={e => setText(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') { setText(''); setOpen(false); } }}
        placeholder="Type guidance to steer the agents..."
        className="flex-1 bg-transparent text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none"
      />
      <button onClick={submit} disabled={!text.trim()}
        className="px-2.5 py-1 rounded-md text-xs bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 disabled:opacity-30 transition-colors cursor-pointer shrink-0">
        Inject
      </button>
      <button onClick={() => { setText(''); setOpen(false); }}
        className="text-zinc-600 hover:text-zinc-400 cursor-pointer shrink-0">
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

// ─── Chat View ─────────────────────────────────────────────────────────────────

function ChatView({ messages, isTyping, input, setInput, sendMessage, activeProject, connected, projectAgents, liveProgress, onSteer }) {
  const endRef      = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, isTyping]);

  const onChange = (e) => {
    setInput(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px';
  };

  // Live progress entries: at most one line per agent, showing current activity
  const liveEntries = Object.entries(liveProgress).filter(([, text]) => text);
  const isSwarmActive = liveEntries.length > 0 || projectAgents.some(a => a.status === 'working');

  return (
    <div className="flex flex-col flex-1 overflow-hidden">

      {/* Live activity strip — one line per agent, replaces in-place */}
      {isSwarmActive && (
        <div className="px-4 py-2 border-b border-zinc-800 bg-zinc-900/40 shrink-0 overflow-hidden">
          <div className="max-w-2xl mx-auto space-y-0.5">
            {liveEntries.map(([agent, text]) => (
              <div key={agent} className="flex items-center gap-2 min-w-0">
                <Loader2 className={`w-3 h-3 shrink-0 animate-spin ${agentColor(agent)}`} />
                <span className={`text-[11px] font-medium shrink-0 ${agentColor(agent)}`}>{agent}</span>
                <span className="text-[11px] text-zinc-500 font-mono truncate">{text}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto px-6 py-8 space-y-3">

          {messages.length === 0 && !isTyping && (
            <div className="flex flex-col items-center justify-center py-24 text-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-center">
                <Bot className="w-5 h-5 text-zinc-600" />
              </div>
              <div>
                <p className="text-sm font-medium text-zinc-300">
                  {activeProject ? activeProject.name : 'No chat selected'}
                </p>
                <p className="text-sm text-zinc-600 mt-1">
                  {activeProject
                    ? 'Send a message to deploy the agent swarm.'
                    : 'Select or create a chat to begin.'}
                </p>
              </div>
            </div>
          )}

          {messages.map((m, i) => {
            if (m.role === 'progress') {
              return <ActivityLine key={i} text={m.text} agent={m.agent} />;
            }

            if (m.role === 'user') {
              return (
                <div key={i} className="flex justify-end pt-1">
                  <div className="max-w-[72%] bg-zinc-800 text-zinc-100 px-4 py-2.5 rounded-2xl rounded-tr-sm text-sm leading-relaxed">
                    {m.text.split('\n').map((line, j) => (
                      <p key={j} className={j > 0 ? 'mt-1.5' : ''}>{line || '\u00A0'}</p>
                    ))}
                  </div>
                </div>
              );
            }

            if (m.role === 'system') {
              return (
                <div key={i} className="flex items-start gap-2.5 pt-1">
                  <div className="w-5 h-5 rounded-md bg-red-500/10 flex items-center justify-center shrink-0 mt-0.5">
                    <Activity className="w-3 h-3 text-red-400" />
                  </div>
                  <p className="text-sm text-red-400/80 leading-relaxed">{m.text}</p>
                </div>
              );
            }

            // assistant — render markdown-ish (newlines → paragraphs, ### headers)
            return (
              <div key={i} className="flex items-start gap-2.5 pt-1">
                <div className="w-5 h-5 rounded-md bg-zinc-800 border border-zinc-700 flex items-center justify-center shrink-0 mt-0.5">
                  <Bot className="w-3 h-3 text-zinc-400" />
                </div>
                <div className="flex-1 min-w-0 text-sm text-zinc-200 leading-relaxed space-y-2">
                  {m.text.split('\n').map((line, j) => {
                    if (line.startsWith('### ')) return <p key={j} className="font-semibold text-zinc-100 mt-1">{line.slice(4)}</p>;
                    if (line.startsWith('## '))  return <p key={j} className="font-semibold text-zinc-100 text-base mt-2">{line.slice(3)}</p>;
                    if (line.startsWith('# '))   return <p key={j} className="font-bold text-zinc-100 text-base mt-2">{line.slice(2)}</p>;
                    if (line.startsWith('- ') || line.startsWith('* ')) return <p key={j} className="pl-3 text-zinc-300">· {line.slice(2)}</p>;
                    return <p key={j} className={line === '' ? 'mt-1' : ''}>{line || '\u00A0'}</p>;
                  })}
                </div>
              </div>
            );
          })}

          {isTyping && (
            <div className="flex items-start gap-2.5 pt-1">
              <div className="w-5 h-5 rounded-md bg-zinc-800 border border-zinc-700 flex items-center justify-center shrink-0 mt-0.5">
                <Bot className="w-3 h-3 text-zinc-400" />
              </div>
              <div className="flex gap-1 items-center h-5">
                {[0, 150, 300].map(d => (
                  <div key={d} className="w-1.5 h-1.5 bg-zinc-600 rounded-full animate-bounce" style={{ animationDelay: `${d}ms` }} />
                ))}
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>
      </div>

      {/* Input */}
      <div className="px-6 pb-6 pt-2 space-y-2">
        <div className="max-w-2xl mx-auto space-y-2">
          {/* Interject bar — visible when swarm is active */}
          {isSwarmActive && (
            <InjectBar onSteer={onSteer} />
          )}
          {/* Main input */}
          <form onSubmit={sendMessage}>
            <div className="flex items-end gap-2 bg-zinc-900 border border-zinc-700 focus-within:border-zinc-500 rounded-xl transition-colors">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={onChange}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(e); } }}
                placeholder={
                  !activeProject ? 'Select a chat first...' :
                  !connected ? 'Connecting...' :
                  isSwarmActive ? 'Queue next message...' : 'Message...'
                }
                disabled={!activeProject || !connected}
                rows={1}
                className="flex-1 bg-transparent px-4 py-3 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none resize-none"
                style={{ minHeight: '46px', maxHeight: '160px' }}
              />
              <button
                type="submit"
                disabled={!input.trim() || !activeProject || !connected}
                className="m-1.5 h-8 w-8 bg-zinc-700 hover:bg-zinc-600 disabled:opacity-30 disabled:cursor-not-allowed rounded-lg transition-colors flex items-center justify-center shrink-0 cursor-pointer"
              >
                <Send className="w-3.5 h-3.5 text-zinc-300" />
              </button>
            </div>
            <p className="text-center text-xs text-zinc-700 mt-1.5">Enter to send · Shift+Enter for newline</p>
          </form>
        </div>
      </div>
    </div>
  );
}

// ─── Agents View ───────────────────────────────────────────────────────────────

function agentRoleHint(name) {
  if (!name) return 'Agent';
  const n = name.toLowerCase();
  if (n.includes('orchestrat')) return 'Orchestrator';
  if (n.includes('research'))   return 'Research';
  if (n.includes('analyst'))    return 'Analysis';
  if (n.includes('writer'))     return 'Writing';
  if (n.includes('develop'))    return 'Development';
  if (n.includes('specialist')) {
    // e.g. "Specialist_Marine_Biology_a3f2" → "Marine Biology"
    const parts = name.split('_').slice(1, -1);
    if (parts.length) return parts.join(' ');
  }
  return 'Specialist';
}

function AgentsView({ roster, activeProjectId, onInspect, wsAction }) {
  const agents = Object.values(roster);
  // Show all agents for the active project, fall back to all if no filter
  const shown = activeProjectId
    ? agents.filter(a => !a.project_id || a.project_id === activeProjectId)
    : agents;

  const working = shown.filter(a => a.status === 'working' || a.status === 'in_progress');
  const idle    = shown.filter(a => a.status !== 'working' && a.status !== 'in_progress');

  if (shown.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center flex-1 text-center gap-3">
        <Cpu className="w-8 h-8 text-zinc-700" />
        <p className="text-sm text-zinc-500">No agents deployed yet.</p>
        <p className="text-xs text-zinc-700">Send a message to start the swarm.</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto space-y-6">

        {/* Active agents */}
        {working.length > 0 && (
          <section>
            <p className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider mb-3">
              Active · {working.length}
            </p>
            <div className="space-y-2">
              {working.map(agent => (
                <div key={agent.name}
                  className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 group">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="relative shrink-0">
                        <div className={`w-8 h-8 rounded-lg bg-zinc-800 flex items-center justify-center`}>
                          <Cpu className={`w-4 h-4 ${agentColor(agent.name)}`} />
                        </div>
                        <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-400 border-2 border-zinc-900 animate-pulse" />
                      </div>
                      <div className="min-w-0">
                        <p className={`text-sm font-medium ${agentColor(agent.name)}`}>{agent.name}</p>
                        <p className="text-[11px] text-zinc-600">{agentRoleHint(agent.name)}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <button onClick={() => onInspect(agent.name)}
                        className="flex items-center gap-1 px-2 py-1 text-[11px] text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 rounded-md transition-all cursor-pointer">
                        <Eye className="w-3 h-3" /> Inspect
                      </button>
                      {agent.current_task && (
                        <button onClick={() => wsAction('stop_task', { task_id: agent.current_task })}
                          className="p-1 text-red-400/60 hover:text-red-400 hover:bg-red-500/10 rounded-md transition-all cursor-pointer" title="Stop">
                          <StopCircle className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                  {agent.current_task && (
                    <p className="mt-3 text-xs text-zinc-500 leading-relaxed border-t border-zinc-800 pt-3 line-clamp-2">
                      {agent.current_task}
                    </p>
                  )}
                  <div className="mt-2 flex items-center gap-3">
                    <span className="text-[10px] text-zinc-700 font-mono">{timeAgo(agent.updated_at)}</span>
                    {agent.source_channel && <ChannelTag channel={agent.source_channel} />}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Idle agents */}
        {idle.length > 0 && (
          <section>
            <p className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider mb-3">
              Standby · {idle.length}
            </p>
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl divide-y divide-zinc-800">
              {idle.map(agent => (
                <div key={agent.name}
                  className="flex items-center gap-3 px-4 py-3 group hover:bg-zinc-800/40 transition-colors">
                  <StatusDot status={agent.status || 'idle'} />
                  <div className="flex-1 min-w-0">
                    <span className="text-xs text-zinc-400">{agent.name}</span>
                    <span className="text-[10px] text-zinc-700 ml-2">{agentRoleHint(agent.name)}</span>
                  </div>
                  <span className="text-[10px] text-zinc-700 font-mono">{timeAgo(agent.updated_at)}</span>
                  <button onClick={() => onInspect(agent.name)}
                    className="opacity-0 group-hover:opacity-100 flex items-center gap-1 px-2 py-1 text-[11px] text-zinc-500 hover:text-zinc-200 hover:bg-zinc-700 rounded-md transition-all cursor-pointer">
                    <Eye className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          </section>
        )}

      </div>
    </div>
  );
}

// ─── Tasks View ────────────────────────────────────────────────────────────────

const STATUS_ORDER = ['in_progress', 'pending', 'paused', 'blocked', 'failed', 'done', 'completed', 'killed'];

function TaskCard({ task, wsAction }) {
  return (
    <div className="flex items-start gap-3 px-4 py-3 hover:bg-zinc-800/30 group transition-colors">
      <StatusDot status={task.status} size="md" className="mt-0.5 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-xs text-zinc-300 leading-relaxed line-clamp-2" title={task.description}>
          {task.description}
        </p>
        <div className="flex items-center gap-2 mt-1">
          <span className={`text-[10px] font-medium ${STATUS_TEXT[task.status] || 'text-zinc-600'}`}>{task.status}</span>
          <span className="text-[10px] text-zinc-700 font-mono">{task.id}</span>
          <span className="text-[10px] text-zinc-700 font-mono ml-auto">{timeAgo(task.created_at)}</span>
        </div>
      </div>
      <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
        {task.status === 'in_progress' && (
          <button onClick={() => wsAction('pause_task', { task_id: task.id })}
            className="p-1 text-amber-400 hover:bg-amber-500/10 rounded cursor-pointer" title="Pause">
            <Pause className="w-3.5 h-3.5" />
          </button>
        )}
        {task.status === 'paused' && (
          <button onClick={() => wsAction('resume_task', { task_id: task.id })}
            className="p-1 text-emerald-400 hover:bg-emerald-500/10 rounded cursor-pointer" title="Resume">
            <Play className="w-3.5 h-3.5" />
          </button>
        )}
        {['in_progress', 'paused', 'pending'].includes(task.status) && (
          <button onClick={() => wsAction('stop_task', { task_id: task.id })}
            className="p-1 text-red-400 hover:bg-red-500/10 rounded cursor-pointer" title="Stop">
            <StopCircle className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}

function TasksView({ tasks, activeProjectId, wsAction }) {
  const [groupBy, setGroupBy] = useState('agent'); // 'agent' | 'status'
  const [search, setSearch]   = useState('');

  const scoped = (activeProjectId ? tasks.filter(t => t.project_id === activeProjectId) : tasks)
    .filter(t => !search || t.description?.toLowerCase().includes(search.toLowerCase()));

  if ((activeProjectId ? tasks.filter(t => t.project_id === activeProjectId) : tasks).length === 0) {
    return (
      <div className="flex flex-col items-center justify-center flex-1 text-center gap-3">
        <List className="w-8 h-8 text-zinc-700" />
        <p className="text-sm text-zinc-500">No tasks yet.</p>
        <p className="text-xs text-zinc-700">Tasks appear when agents are deployed.</p>
      </div>
    );
  }

  // ── Group by Agent ──────────────────────────────────────────────
  const renderByAgent = () => {
    const groups = {};
    for (const t of scoped) {
      const key = t.assigned_to || 'Unassigned';
      if (!groups[key]) groups[key] = [];
      groups[key].push(t);
    }
    // Sort groups: active agents first, then by name
    const sorted = Object.entries(groups).sort(([a], [b]) => {
      if (a === 'Unassigned') return 1;
      if (b === 'Unassigned') return -1;
      const aActive = groups[a].some(t => t.status === 'in_progress');
      const bActive = groups[b].some(t => t.status === 'in_progress');
      if (aActive && !bActive) return -1;
      if (!aActive && bActive) return 1;
      return a.localeCompare(b);
    });

    return sorted.map(([agentName, agentTasks]) => {
      const active = agentTasks.filter(t => t.status === 'in_progress' || t.status === 'pending');
      const done   = agentTasks.filter(t => ['done','completed','killed','failed'].includes(t.status));
      const sorted = [...active, ...done].sort((a, b) =>
        STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status));
      return (
        <section key={agentName}>
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-zinc-800 sticky top-0 bg-zinc-950 z-10">
            {active.length > 0 && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shrink-0" />}
            <span className={`text-xs font-medium ${agentName === 'Unassigned' ? 'text-zinc-600' : agentColor(agentName)}`}>
              {agentName}
            </span>
            <span className="text-[10px] text-zinc-700">{agentTasks.length} task{agentTasks.length !== 1 ? 's' : ''}</span>
            {active.length > 0 && (
              <span className="text-[10px] text-emerald-600 ml-auto">{active.length} active</span>
            )}
          </div>
          <div className="divide-y divide-zinc-800/40">
            {sorted.map(t => <TaskCard key={t.id} task={t} wsAction={wsAction} />)}
          </div>
        </section>
      );
    });
  };

  // ── Group by Status ─────────────────────────────────────────────
  const renderByStatus = () => {
    const groups = {};
    for (const t of scoped) {
      if (!groups[t.status]) groups[t.status] = [];
      groups[t.status].push(t);
    }
    return STATUS_ORDER.filter(s => groups[s]?.length).map(status => (
      <section key={status}>
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-zinc-800 sticky top-0 bg-zinc-950 z-10">
          <StatusDot status={status} />
          <span className={`text-xs font-medium ${STATUS_TEXT[status] || 'text-zinc-500'}`}>{status}</span>
          <span className="text-[10px] text-zinc-700">{groups[status].length}</span>
        </div>
        <div className="divide-y divide-zinc-800/40">
          {groups[status].map(t => <TaskCard key={t.id} task={t} wsAction={wsAction} />)}
        </div>
      </section>
    ));
  };

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Toolbar */}
      <div className="px-4 py-2.5 border-b border-zinc-800 flex items-center gap-3 shrink-0">
        <div className="flex items-center gap-0.5 bg-zinc-900 rounded-lg p-0.5 border border-zinc-800">
          {[{ key: 'agent', label: 'By Agent' }, { key: 'status', label: 'By Status' }].map(v => (
            <button key={v.key} onClick={() => setGroupBy(v.key)}
              className={`px-2.5 py-1 rounded-md text-xs transition-colors cursor-pointer ${
                groupBy === v.key ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
              }`}>
              {v.label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2 border border-zinc-800 rounded-md px-2.5 py-1">
          <Filter className="w-3 h-3 text-zinc-600" />
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Filter tasks..."
            className="bg-transparent text-xs text-zinc-300 placeholder:text-zinc-600 focus:outline-none w-28" />
        </div>
        <span className="text-[10px] text-zinc-700 font-mono">{scoped.length} tasks</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {scoped.length === 0
          ? <p className="text-center text-xs text-zinc-600 py-10">No tasks match filter.</p>
          : groupBy === 'agent' ? renderByAgent() : renderByStatus()
        }
      </div>
    </div>
  );
}

// ─── Logs View ─────────────────────────────────────────────────────────────────

function LogsView({ telemetry }) {
  const [agentFilter, setAgentFilter] = useState('');
  const [paused, setPaused]           = useState(false);
  const [frozen, setFrozen]           = useState([]);
  const topRef                        = useRef(null);

  useEffect(() => {
    if (!paused) topRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [telemetry, paused]);

  const togglePause = () => {
    if (!paused) setFrozen([...telemetry]);
    setPaused(p => !p);
  };

  const logs   = paused ? frozen : telemetry;
  const agents = [...new Set(logs.map(l => l.agent).filter(Boolean))];
  const shown  = agentFilter ? logs.filter(l => l.agent === agentFilter) : logs;

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <div className="px-4 py-2.5 border-b border-zinc-800 flex items-center gap-3 shrink-0">
        <span className="text-xs text-zinc-500 font-medium">Telemetry</span>
        <span className="text-xs text-zinc-700 font-mono">{shown.length} events</span>
        <div className="flex-1" />
        {agents.length > 0 && (
          <select value={agentFilter} onChange={e => setAgentFilter(e.target.value)}
            className="bg-transparent border border-zinc-800 rounded-md px-2 py-1 text-xs text-zinc-400 focus:outline-none cursor-pointer">
            <option value="">All agents</option>
            {agents.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        )}
        <button onClick={togglePause}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs transition-colors cursor-pointer ${
            paused ? 'text-emerald-400 hover:bg-zinc-800' : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800'
          }`}>
          {paused ? <><Play className="w-3 h-3" /> Resume</> : <><Pause className="w-3 h-3" /> Pause</>}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto font-mono text-[11px] leading-5 py-2">
        <div ref={topRef} />
        {shown.length === 0 && (
          <p className="text-zinc-700 text-center py-16">No events yet. Activity streams here in real time.</p>
        )}
        {shown.map((log, i) => (
          <div key={log.id || i}
            className="flex items-start gap-3 px-4 py-0.5 hover:bg-zinc-800/30 transition-colors">
            <span className="text-zinc-700 shrink-0 w-14 tabular-nums select-none">{log.ts}</span>
            <span className={`shrink-0 w-32 truncate ${agentColor(log.agent)}`}>[{log.agent}]</span>
            <span className={`shrink-0 w-16 ${ACTION_COLOR[log.action] || 'text-zinc-500'}`}>{log.action}</span>
            <span className="text-zinc-600 shrink-0 w-20 truncate">{log.tool}</span>
            <span className="text-zinc-700 flex-1 truncate">{log.result || log.args || ''}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Agent Inspect Modal ───────────────────────────────────────────────────────

function AgentModal({ agent, agentData, traces, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-8 bg-black/60 backdrop-blur-sm"
      onClick={onClose}>
      <div className="w-full max-w-lg max-h-[80vh] bg-zinc-900 border border-zinc-700/60 rounded-xl overflow-hidden shadow-2xl flex flex-col"
        onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-3">
            <StatusDot status={agentData?.status || 'idle'} size="md" />
            <div>
              <p className={`text-sm font-medium ${agentColor(agent)}`}>{agent}</p>
              <p className="text-xs text-zinc-500">
                {agentData?.status || 'idle'}
                {agentData?.current_task ? ` — ${agentData.current_task.slice(0, 60)}` : ''}
              </p>
            </div>
          </div>
          <button onClick={onClose}
            className="w-7 h-7 flex items-center justify-center text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 rounded-md transition-all cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="overflow-y-auto flex-1 p-5 space-y-4">
          {!(traces?.length)
            ? <p className="text-xs text-zinc-600 text-center py-10">No trace recorded yet.</p>
            : traces.map((t, i) => (
              <div key={i} className="space-y-1">
                <span className="text-[10px] text-zinc-600 font-mono">{t.ts} · {t.type}</span>
                <p className="text-xs text-zinc-300 whitespace-pre-wrap break-words leading-relaxed">{t.content}</p>
              </div>
            ))
          }
        </div>
      </div>
    </div>
  );
}

// ─── Project List (sidebar) ────────────────────────────────────────────────────

function ProjectList({ projects, activeProjectId, onSelect, onDelete, onStop, onRename }) {
  const [menuFor, setMenuFor]       = useState(null); // project id with open menu
  const [renaming, setRenaming]     = useState(null); // project id being renamed
  const [renameVal, setRenameVal]   = useState('');
  const [confirming, setConfirming] = useState(null); // project id pending delete confirm
  const menuRef = useRef(null);

  // Close menu on outside click
  useEffect(() => {
    const handler = (e) => { if (menuRef.current && !menuRef.current.contains(e.target)) setMenuFor(null); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const startRename = (p) => {
    setRenameVal(p.name);
    setRenaming(p.id);
    setMenuFor(null);
  };

  const commitRename = (pid) => {
    if (renameVal.trim()) onRename(pid, renameVal.trim());
    setRenaming(null);
  };

  return (
    <nav className="flex-1 overflow-y-auto px-3 pb-3 space-y-0.5 mt-1">
      {projects.length === 0 && (
        <p className="text-xs text-zinc-700 px-2.5 py-2">No chats yet.</p>
      )}
      {projects.map(p => {
        const isActive = p.id === activeProjectId;
        const hasActivity = p.active_agents > 0 || p.active_tasks > 0;
        return (
          <div key={p.id} className="relative group">
            {renaming === p.id ? (
              <input
                autoFocus
                value={renameVal}
                onChange={e => setRenameVal(e.target.value)}
                onBlur={() => commitRename(p.id)}
                onKeyDown={e => {
                  if (e.key === 'Enter') commitRename(p.id);
                  if (e.key === 'Escape') setRenaming(null);
                }}
                className="w-full px-2.5 py-2 text-xs bg-zinc-800 border border-zinc-600 rounded-md text-zinc-100 focus:outline-none"
              />
            ) : (
              <button onClick={() => onSelect(p.id)}
                className={`w-full text-left flex items-start gap-2 px-2.5 py-2 rounded-md transition-colors cursor-pointer ${
                  isActive ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/60'
                }`}>
                <MessageSquare className="w-3.5 h-3.5 shrink-0 mt-0.5 opacity-50" />
                <div className="min-w-0 flex-1">
                  <span className="text-xs truncate block">{p.name}</span>
                  {hasActivity && (
                    <span className="text-[10px] text-emerald-500/60 mt-0.5 block">
                      {p.active_agents > 0 ? `${p.active_agents} agent${p.active_agents !== 1 ? 's' : ''} active` : `${p.active_tasks} running`}
                    </span>
                  )}
                </div>
                {/* Context menu trigger */}
                <button
                  onClick={e => { e.stopPropagation(); setMenuFor(menuFor === p.id ? null : p.id); }}
                  className="opacity-0 group-hover:opacity-100 w-5 h-5 flex items-center justify-center text-zinc-500 hover:text-zinc-200 rounded transition-all cursor-pointer shrink-0 mt-0.5"
                  title="Options">
                  <span className="text-base leading-none tracking-widest" style={{ letterSpacing: '-1px' }}>···</span>
                </button>
              </button>
            )}

            {/* Context menu */}
            {menuFor === p.id && (
              <div ref={menuRef}
                className="absolute right-0 top-8 z-50 w-44 bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl overflow-hidden py-1">
                <button onClick={() => startRename(p)}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 transition-colors cursor-pointer">
                  <span className="text-zinc-500">✎</span> Rename
                </button>
                {hasActivity && (
                  <button onClick={() => { onStop(p.id); setMenuFor(null); }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-amber-400 hover:bg-amber-500/10 transition-colors cursor-pointer">
                    <Pause className="w-3.5 h-3.5" /> Stop All Tasks
                  </button>
                )}
                <div className="mx-2 my-1 border-t border-zinc-800" />
                {confirming === p.id ? (
                  <div className="px-3 py-2">
                    <p className="text-[11px] text-zinc-400 mb-2">Delete this chat and all its data?</p>
                    <div className="flex gap-1.5">
                      <button onClick={() => { onDelete(p.id); setMenuFor(null); setConfirming(null); }}
                        className="flex-1 py-1 text-[11px] bg-red-500/20 text-red-400 hover:bg-red-500/30 rounded-md transition-colors cursor-pointer">
                        Delete
                      </button>
                      <button onClick={() => setConfirming(null)}
                        className="flex-1 py-1 text-[11px] bg-zinc-800 text-zinc-400 hover:bg-zinc-700 rounded-md transition-colors cursor-pointer">
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <button onClick={() => setConfirming(p.id)}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-red-400 hover:bg-red-500/10 transition-colors cursor-pointer">
                    <X className="w-3.5 h-3.5" /> Delete Chat
                  </button>
                )}
              </div>
            )}
          </div>
        );
      })}
    </nav>
  );
}

// ─── Main App ──────────────────────────────────────────────────────────────────

const TABS = [
  { key: 'chat',   label: 'Chat',   Icon: MessageSquare },
  { key: 'agents', label: 'Agents', Icon: Cpu           },
  { key: 'tasks',  label: 'Tasks',  Icon: List          },
  { key: 'logs',   label: 'Logs',   Icon: Terminal      },
];

export default function App() {
  const [ws, setWs]                   = useState(null);
  const [connected, setConnected]     = useState(false);
  const [activeTab, setActiveTab]     = useState('chat');
  const [projects, setProjects]       = useState([]);
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const [activeProjectId, setActiveProjectId] = useState(
    () => localStorage.getItem('cmas_project_id') || ''
  );

  const projectSessionsRef = useRef(null);
  if (projectSessionsRef.current === null) {
    try { projectSessionsRef.current = JSON.parse(localStorage.getItem('cmas_project_sessions') || '{}'); }
    catch { projectSessionsRef.current = {}; }
  }
  const getSessionForProject = useCallback((pid) => pid ? (projectSessionsRef.current[pid] || '') : '', []);
  const storeSessionForProject = useCallback((pid, sid) => {
    if (!pid || !sid) return;
    projectSessionsRef.current[pid] = sid;
    localStorage.setItem('cmas_project_sessions', JSON.stringify(projectSessionsRef.current));
  }, []);

  const [sessionId, setSessionId] = useState(() => {
    const pid = localStorage.getItem('cmas_project_id') || '';
    try {
      const map = JSON.parse(localStorage.getItem('cmas_project_sessions') || '{}');
      return (pid && map[pid]) || '';
    } catch { return ''; }
  });

  const [messages, setMessages]       = useState([]);
  const [liveProgress, setLiveProgress] = useState({});
  const [roster, setRoster]           = useState({});
  const [tasks, setTasks]             = useState([]);
  const [telemetry, setTelemetry]     = useState([]);
  const [traces, setTraces]           = useState({});
  const [input, setInput]             = useState('');
  const [isTyping, setIsTyping]       = useState(false);
  const [inspectAgent, setInspectAgent] = useState(null);

  const activeProjectRef = useRef(activeProjectId);
  useEffect(() => { activeProjectRef.current = activeProjectId; }, [activeProjectId]);
  const sessionIdRef = useRef(sessionId);
  useEffect(() => { sessionIdRef.current = sessionId; }, [sessionId]);

  // ── Data ────────────────────────────────────────────────────────
  const loadProjects = useCallback(async () => {
    try { const r = await fetch('/api/projects'); if (r.ok) setProjects(await r.json()); } catch {}
  }, []);

  const loadTasks = useCallback(async (pid) => {
    try {
      const r = await fetch(pid ? `/api/tasks?project_id=${pid}` : '/api/tasks');
      if (r.ok) setTasks(await r.json());
    } catch {}
  }, []);

  const loadAgents = useCallback(async (pid) => {
    try {
      const r = await fetch(pid ? `/api/agents?project_id=${pid}` : '/api/agents');
      if (r.ok) {
        const list = await r.json();
        setRoster(prev => {
          const next = { ...prev };
          list.forEach(a => { next[a.name] = { ...next[a.name], ...a }; });
          return next;
        });
      }
    } catch {}
  }, []);

  useEffect(() => { loadProjects(); }, [loadProjects]);
  useEffect(() => {
    if (activeTab === 'tasks')  loadTasks(activeProjectId);
    if (activeTab === 'agents') loadAgents(activeProjectId);
  }, [activeTab, activeProjectId, loadTasks, loadAgents]);

  // ── WebSocket ───────────────────────────────────────────────────
  useEffect(() => {
    let socket = null, timer = null, dead = false;

    const connect = () => {
      if (dead) return;
      const pid = activeProjectRef.current;
      const sid = sessionIdRef.current;
      const url = `ws://${window.location.host}/ws?user_id=web_user&project_id=${encodeURIComponent(pid)}${sid ? `&session_id=${encodeURIComponent(sid)}` : ''}`;
      socket = new WebSocket(url);

      socket.onopen = () => {
        setConnected(true);
        socket.send(JSON.stringify({ type: 'get_tasks', project_id: pid }));
        if (sid) socket.send(JSON.stringify({ type: 'get_history' }));
      };
      socket.onclose  = () => { if (!dead) { setConnected(false); timer = setTimeout(connect, 3000); } };
      socket.onerror  = () => { socket.close(); };
      socket.onmessage = (e) => { try { handleMessage(JSON.parse(e.data)); } catch {} };
      setWs(socket);
    };

    connect();
    return () => { dead = true; clearTimeout(timer); socket?.close(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProjectId]);

  // ── Message handler ─────────────────────────────────────────────
  const handleMessage = (data) => {
    const pid = activeProjectRef.current;
    switch (data.type) {
      case 'session':
        if (data.session_id) {
          setSessionId(data.session_id);
          const currentPid = activeProjectRef.current;
          if (currentPid) storeSessionForProject(currentPid, data.session_id);
        }
        break;
      case 'history':
        setMessages((data.messages || []).map(m => ({ role: m.role, text: m.content })));
        break;
      case 'roster_init': {
        const r = {};
        (data.agents || []).forEach(a => { r[a.name] = a; });
        setRoster(r);
        break;
      }
      case 'agent_status':
        setRoster(prev => ({
          ...prev,
          [data.agent]: {
            ...prev[data.agent],
            name: data.agent, status: data.status, current_task: data.task,
            project_id: data.project_id || prev[data.agent]?.project_id || '',
            updated_at: Date.now() / 1000,
          }
        }));
        // Remove from live strip when agent goes idle so animations stop
        if (data.status === 'idle' || data.status === 'error') {
          setLiveProgress(prev => {
            const next = { ...prev };
            delete next[data.agent];
            return next;
          });
        }
        break;
      case 'task_update':
        setTasks(prev => {
          const idx = prev.findIndex(t => t.id === data.task.id);
          if (idx >= 0) { const n = [...prev]; n[idx] = data.task; return n; }
          return [data.task, ...prev];
        });
        break;
      case 'task_list':  setTasks(data.tasks || []); break;
      case 'trace':
        setTraces(prev => ({
          ...prev,
          [data.agent]: [
            { type: data.step_type, content: data.content, ts: data.ts },
            ...(prev[data.agent] || [])
          ].slice(0, 50)
        }));
        break;
      case 'telemetry':
        if (!data.project_id || data.project_id === pid)
          setTelemetry(prev => [{ ...data, id: Date.now() + Math.random() }, ...prev].slice(0, 300));
        break;
      case 'typing':   setIsTyping(data.status); break;
      case 'progress': {
        const agent = data.agent || '';
        const text  = data.text  || '';
        // Always update the live activity strip (per-agent, replaces in-place)
        setLiveProgress(prev => ({ ...prev, [agent || '_']: text }));
        // Only add to chat for major orchestrator-level phase transitions
        // Agent-level chatter (searching, starting tasks, completing tasks) stays in the strip only
        const isOrchestratorPhase = agent === 'Orchestrator' &&
          /pre-screening|mcts|decomposing|synthesiz|evaluating|metacog|launching/i.test(text);
        if (isOrchestratorPhase) {
          setMessages(prev => [...prev, { role: 'progress', text, agent }]);
        }
        break;
      }
      case 'project_created':
        setProjects(prev => [data, ...prev]);
        selectProject(data.id);
        break;
      case 'project_renamed':
        setProjects(prev => prev.map(p => p.id === data.project_id ? { ...p, name: data.name } : p));
        break;
      case 'project_deleted':
        setProjects(prev => prev.filter(p => p.id !== data.project_id));
        if (activeProjectRef.current === data.project_id) {
          setActiveProjectId('');
          localStorage.removeItem('cmas_project_id');
          setMessages([]); setLiveProgress({}); setTasks([]); setRoster({});
        }
        break;
      case 'project_stopped':
        // Clear live activity strip so stale animations disappear immediately
        setLiveProgress({});
        setRoster(prev => {
          const next = { ...prev };
          Object.keys(next).forEach(name => {
            if (next[name].project_id === data.project_id) {
              next[name] = { ...next[name], status: 'idle', current_task: '' };
            }
          });
          return next;
        });
        break;
      case 'message':
      case 'proactive':
        setMessages(prev => [...prev, { role: 'assistant', text: data.text }]);
        setIsTyping(false);
        break;
      case 'error':
        setMessages(prev => [...prev, { role: 'system', text: data.text }]);
        setIsTyping(false);
        break;
    }
  };

  // ── Actions ─────────────────────────────────────────────────────
  const sendMessage = (e) => {
    e?.preventDefault();
    const text = input.trim();
    if (!text || !ws || ws.readyState !== WebSocket.OPEN || !activeProjectId) return;
    setMessages(prev => [...prev, { role: 'user', text }]);
    ws.send(JSON.stringify({ type: 'chat', text, project_id: activeProjectId }));
    setInput('');
  };

  const wsAction = (type, extra = {}) => {
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type, ...extra }));
  };

  const selectProject = (pid) => {
    localStorage.setItem('cmas_project_id', pid);
    setActiveProjectId(pid);
    setSessionId(getSessionForProject(pid));
    setMessages([]); setLiveProgress({}); setTraces({}); setTasks([]); setTelemetry([]); setRoster({});
  };

  const createChat = () => {
    if (ws?.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: 'create_project', name: 'New Chat', focus: '' }));
  };

  const deleteProject = (pid) => {
    if (ws?.readyState === WebSocket.OPEN)
      ws.send(JSON.stringify({ type: 'delete_project', project_id: pid }));
  };

  const stopProject = (pid) => {
    if (ws?.readyState === WebSocket.OPEN)
      ws.send(JSON.stringify({ type: 'stop_project', project_id: pid }));
  };

  const renameProject = (pid, name) => {
    if (ws?.readyState === WebSocket.OPEN && name.trim())
      ws.send(JSON.stringify({ type: 'rename_project', project_id: pid, name: name.trim() }));
  };

  const injectSteer = (text) => {
    if (ws?.readyState === WebSocket.OPEN && text.trim())
      ws.send(JSON.stringify({ type: 'steer', text: text.trim() }));
  };

  // ── Derived ─────────────────────────────────────────────────────
  const activeProject = projects.find(p => p.id === activeProjectId);
  const allAgents     = Object.values(roster);
  const projectAgents = allAgents.filter(a => a.project_id === activeProjectId);
  const activeAgents  = projectAgents.filter(a => a.status === 'working').length;
  const projectTasks  = tasks.filter(t => t.project_id === activeProjectId);
  const activeTasks   = projectTasks.filter(t => t.status === 'in_progress').length;

  // Right panel only makes sense in chat tab
  const showRightPanel = activeTab === 'chat';

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-100 overflow-hidden">

      {/* ── Sidebar ── */}
      <aside className="w-52 flex flex-col border-r border-zinc-800 shrink-0">
        <div className="px-4 h-12 flex items-center gap-2.5 border-b border-zinc-800">
          <div className="w-6 h-6 rounded-md bg-zinc-800 border border-zinc-700 flex items-center justify-center">
            <Zap className="w-3.5 h-3.5 text-zinc-300" />
          </div>
          <span className="text-sm font-semibold text-zinc-100 tracking-tight">CMAS</span>
          <div className={`ml-auto w-1.5 h-1.5 rounded-full ${connected ? 'bg-emerald-500' : 'bg-red-500 animate-pulse'}`}
            title={connected ? 'Connected' : 'Reconnecting'} />
        </div>

        <div className="px-3 pt-3 pb-1">
          <button onClick={createChat} disabled={!connected}
            className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer">
            <Plus className="w-3.5 h-3.5" />
            New Chat
          </button>
        </div>

        <ProjectList
          projects={projects}
          activeProjectId={activeProjectId}
          onSelect={selectProject}
          onDelete={deleteProject}
          onStop={stopProject}
          onRename={renameProject}
        />
      </aside>

      {/* ── Main ── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

        <header className="h-12 border-b border-zinc-800 flex items-center px-4 gap-1 shrink-0">
          <nav className="flex items-center gap-0.5">
            {TABS.map(({ key, label, Icon }) => {
              const count  = key === 'agents' ? (activeAgents || null) : key === 'tasks' ? (activeTasks || null) : null;
              const isActive = activeTab === key;
              return (
                <button key={key} onClick={() => setActiveTab(key)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs transition-colors cursor-pointer ${
                    isActive ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/60'
                  }`}>
                  <Icon className="w-3.5 h-3.5" />
                  {label}
                  {count != null && (
                    <span className="text-[10px] font-mono text-emerald-500">{count}</span>
                  )}
                </button>
              );
            })}
          </nav>

          <div className="flex-1" />

          <div className="flex items-center gap-3 text-xs text-zinc-600">
            {activeProject && (
              <span className="text-zinc-400 truncate max-w-[200px]">{activeProject.name}</span>
            )}
            {activeAgents > 0 && (
              <>
                <span className="flex items-center gap-1.5 text-emerald-500">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  {activeAgents} agent{activeAgents !== 1 ? 's' : ''} running
                </span>
                <button onClick={() => stopProject(activeProjectId)}
                  className="flex items-center gap-1.5 px-2 py-1 rounded-md text-red-400 hover:bg-red-500/10 transition-colors cursor-pointer border border-red-500/20 hover:border-red-500/40">
                  <StopCircle className="w-3 h-3" /> Stop All
                </button>
              </>
            )}
          </div>
        </header>

        {/* Content + right panel */}
        <div className="flex-1 flex overflow-hidden">
          <div className="flex-1 flex flex-col overflow-hidden">
            {activeTab === 'chat' && (
              <ChatView messages={messages} isTyping={isTyping} input={input}
                setInput={setInput} sendMessage={sendMessage} activeProject={activeProject}
                connected={connected} projectAgents={projectAgents} liveProgress={liveProgress}
                onSteer={injectSteer} />
            )}
            {activeTab === 'agents' && (
              <AgentsView roster={roster} activeProjectId={activeProjectId}
                onInspect={setInspectAgent} wsAction={wsAction} />
            )}
            {activeTab === 'tasks' && (
              <TasksView tasks={tasks} activeProjectId={activeProjectId} wsAction={wsAction} />
            )}
            {activeTab === 'logs' && <LogsView telemetry={telemetry} />}
          </div>

          {/* Right panel — chat tab only */}
          {showRightPanel && (
            <RightPanel
              projectAgents={projectAgents}
              projectTasks={projectTasks}
              liveProgress={liveProgress}
              isOpen={rightPanelOpen}
              onToggle={() => setRightPanelOpen(o => !o)}
            />
          )}
        </div>
      </div>

      {inspectAgent && (
        <AgentModal agent={inspectAgent} agentData={roster[inspectAgent]}
          traces={traces[inspectAgent]} onClose={() => setInspectAgent(null)} />
      )}

      <style>{`
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #3f3f46; border-radius: 4px; }
        * { scrollbar-width: thin; scrollbar-color: #3f3f46 transparent; }
      `}</style>
    </div>
  );
}
