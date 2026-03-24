import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  Send, Plus, Bot, Activity, X, MessageSquare,
  Pause, StopCircle, Play, Terminal, List, Filter,
  Globe, Cpu, Eye, Search, FileText, Code, Command,
  Loader2, CheckCircle, Zap, ChevronRight, ChevronLeft,
  Sparkles, Network, Crown, Users, ArrowRight, Circle,
  GitBranch, Hash
} from 'lucide-react';

// ─── Status config ─────────────────────────────────────────────────────────────

const STATUS_DOT = {
  working:     'bg-emerald-400 animate-pulse',
  in_progress: 'bg-emerald-400 animate-pulse',
  planning:    'bg-violet-400 animate-pulse',
  executing:   'bg-blue-400 animate-pulse',
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
  planning:    'text-violet-400',
  executing:   'text-blue-400',
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

// ─── Color system ──────────────────────────────────────────────────────────────

const TEAM_COLORS = [
  { bg: 'bg-sky-500/15', border: 'border-sky-500/30', text: 'text-sky-400', dot: 'bg-sky-400' },
  { bg: 'bg-violet-500/15', border: 'border-violet-500/30', text: 'text-violet-400', dot: 'bg-violet-400' },
  { bg: 'bg-amber-500/15', border: 'border-amber-500/30', text: 'text-amber-400', dot: 'bg-amber-400' },
  { bg: 'bg-emerald-500/15', border: 'border-emerald-500/30', text: 'text-emerald-400', dot: 'bg-emerald-400' },
  { bg: 'bg-rose-500/15', border: 'border-rose-500/30', text: 'text-rose-400', dot: 'bg-rose-400' },
  { bg: 'bg-cyan-500/15', border: 'border-cyan-500/30', text: 'text-cyan-400', dot: 'bg-cyan-400' },
  { bg: 'bg-orange-500/15', border: 'border-orange-500/30', text: 'text-orange-400', dot: 'bg-orange-400' },
  { bg: 'bg-pink-500/15', border: 'border-pink-500/30', text: 'text-pink-400', dot: 'bg-pink-400' },
];

function teamColorSet(teamName) {
  if (!teamName) return TEAM_COLORS[0];
  let hash = 0;
  for (let i = 0; i < teamName.length; i++) hash = (hash * 31 + teamName.charCodeAt(i)) & 0xFFFF;
  return TEAM_COLORS[hash % TEAM_COLORS.length];
}

function agentColor(name) {
  if (!name) return 'text-zinc-500';
  const n = name.toLowerCase();
  if (n.includes('composer'))      return 'text-amber-300';
  if (n.includes('orchestrat'))    return 'text-violet-400';
  if (n.startsWith('team:'))       return teamColorSet(name.slice(5)).text;
  if (n.includes('research'))      return 'text-sky-400';
  if (n.includes('analyst'))       return 'text-amber-400';
  if (n.includes('writer'))        return 'text-emerald-400';
  if (n.includes('develop'))       return 'text-orange-400';
  if (n.includes('design'))        return 'text-pink-400';
  if (n.includes('mcts') || n.includes('engine') || n.includes('brain')) return 'text-purple-400';
  const COLORS = [
    'text-sky-400', 'text-amber-400', 'text-emerald-400', 'text-rose-400',
    'text-indigo-400', 'text-cyan-400', 'text-lime-400', 'text-pink-400',
  ];
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) & 0xFFFF;
  return COLORS[hash % COLORS.length];
}

// Parse team membership from agent name pattern: "TeamName_Role_id"
function parseAgentTeam(agentName) {
  if (!agentName) return null;
  // Known pattern from team.py: "{spec.name}_{role}_{id}"
  // Team names can contain spaces, roles have underscores
  // We detect by looking for known team patterns or fall back to prefix matching
  const parts = agentName.split('_');
  if (parts.length >= 3) {
    // The last part is the sub-agent id (e.g., "worker_1"), second-to-last group is role
    // Try to find where team name ends — it's everything before the role+id portion
    // Heuristic: if name has "Team" in it, split on that boundary
    const teamMatch = agentName.match(/^(.+?(?:Team|Research|Legal|Design|Marketing|Engineering|Operations|Strategy|Finance|Content|Analysis).*?)_/i);
    if (teamMatch) return teamMatch[1].replace(/_/g, ' ');
    // Fallback: first segment(s) before a known role keyword
    const roleKeywords = ['researcher', 'analyst', 'writer', 'developer', 'specialist', 'designer', 'lead', 'manager', 'coordinator', 'expert', 'strategist', 'engineer'];
    for (let i = 1; i < parts.length; i++) {
      if (roleKeywords.some(kw => parts[i].toLowerCase().includes(kw))) {
        return parts.slice(0, i).join(' ');
      }
    }
  }
  return null;
}

// ─── Display Humanizers ────────────────────────────────────────────────────────
// Turn raw agent names like "Design Team_UX_Researcher_worker_1" into "UX Researcher"
// and raw progress text into clean, user-friendly descriptions.

function humanAgentName(raw) {
  if (!raw) return 'Agent';
  // Special prefixes
  if (raw === 'Composer') return 'Composer';
  if (raw === 'Orchestrator') return 'Orchestrator';
  if (raw.startsWith('Team:')) return raw.slice(5);

  // Pattern: "TeamName_Role_SubId" → extract role portion
  // Agent names from team.py: "{spec.name}_{role}_{id}"
  // e.g. "Design Team_UX_Researcher_worker_1" → "UX Researcher"
  const parts = raw.split('_');
  if (parts.length >= 3) {
    // Find the role keywords to locate where the role starts
    const roleKeywords = ['researcher', 'analyst', 'writer', 'developer', 'specialist',
      'designer', 'lead', 'manager', 'coordinator', 'expert', 'strategist', 'engineer',
      'reviewer', 'planner', 'architect', 'tester', 'editor', 'compiler', 'auditor'];
    // Walk from end backward; the last part is the id (like "worker_1" or just "1")
    // Strip trailing id parts (numeric or very short)
    let endIdx = parts.length;
    while (endIdx > 1 && (parts[endIdx - 1].match(/^\d+$/) || parts[endIdx - 1] === 'worker')) endIdx--;
    // Now find where the role starts (first part that's a role keyword)
    let startIdx = 0;
    for (let i = 0; i < endIdx; i++) {
      if (roleKeywords.some(kw => parts[i].toLowerCase().includes(kw))) {
        startIdx = i;
        break;
      }
    }
    // If we found a role keyword, use from there to endIdx
    if (startIdx > 0 && startIdx < endIdx) {
      return parts.slice(startIdx, endIdx).join(' ').replace(/_/g, ' ');
    }
    // Fallback: skip first part (team name), take middle parts
    if (endIdx > 1) {
      return parts.slice(1, endIdx).join(' ').replace(/_/g, ' ');
    }
  }
  // Simple cleanup: replace underscores, trim IDs
  return raw.replace(/_/g, ' ').replace(/\s+\d+$/, '').trim() || raw;
}

function humanProgressText(raw, agentName) {
  if (!raw) return '';
  let text = raw;

  // Strip the agent name prefix if the progress starts with it
  // e.g. "Design Team_UX_Researcher_worker_1 searching: ..." → "Searching: ..."
  if (agentName && text.startsWith(agentName)) {
    text = text.slice(agentName.length).trim();
    // Remove leading punctuation from stripping
    text = text.replace(/^[:\-–—]\s*/, '');
  }

  // Clean up tool-use patterns from agent.py _fmt_progress:
  //   "searching: \"query\"" → "Searching for query"
  //   "using web_search" → "Searching the web"
  //   "deploying specialist agent: \"task\"" → "Deploying specialist: task"
  //   "running Python: code..." → "Running code"
  //   "writing: filename" → "Writing filename"
  //   "running: command" → "Running command"
  //   "using tool_name" → "Using tool name"
  text = text
    // "searching: \"query\"" → "Searching for query"
    .replace(/^searching:\s*"?([^"]*)"?$/i, (_, q) => `Searching for ${q}`)
    // "deploying specialist agent: \"task\"" → "Deploying specialist: task"
    .replace(/^deploying\s+(\w+)\s+agent:\s*"?([^"]*)"?$/i, (_, role, task) => `Deploying ${role}: ${task}`)
    // "→ AgentName: message" → "Messaging AgentName: message"
    .replace(/^→\s*(.+?):\s*(.+)$/, (_, to, msg) => `Talking to ${humanAgentName(to)}: ${msg}`)
    // "using web_search" → "Searching the web"
    .replace(/^using web_search$/i, 'Searching the web')
    // "using read_file" → "Reading a file"
    .replace(/^using read_file$/i, 'Reading a file')
    // "using write_file" → "Writing a file"
    .replace(/^using write_file$/i, 'Writing a file')
    // "using run_python" → "Running Python code"
    .replace(/^using run_python$/i, 'Running Python code')
    // "using run_command" → "Running a command"
    .replace(/^using run_command$/i, 'Running a command')
    // "using apply_framework" → "Applying a framework"
    .replace(/^using apply_framework$/i, 'Applying a framework')
    // "using send_message" → "Sending a message"
    .replace(/^using send_message$/i, 'Sending a message')
    // "using delegate_task" → "Delegating a task"
    .replace(/^using delegate_task$/i, 'Delegating a task')
    // Generic "using tool_name" → "Using tool name" (humanize tool name)
    .replace(/^using (\w+)$/i, (_, tool) => `Using ${tool.replace(/_/g, ' ')}`)
    // "running Python: code_line" → "Running Python code"
    .replace(/^running Python:\s*.+$/i, 'Running Python code')
    // "running: cmd" → "Running cmd"
    .replace(/^running:\s*(.+)$/i, (_, cmd) => `Running ${cmd}`)
    // "writing: filename" → "Writing filename"
    .replace(/^writing:\s*(.+)$/i, (_, file) => `Writing ${file}`);

  // Remove stray JSON/bracket artifacts: {...}, [...], raw JSON objects
  text = text
    .replace(/\{[^}]{0,20}\}/g, '')       // short {key: val}
    .replace(/\[[^\]]{0,20}\]/g, '')       // short [items]
    .replace(/"(\w+)":/g, '')              // "key":
    .replace(/[{}[\]]/g, '')               // remaining brackets
    .trim();

  // Replace raw underscored agent names in the text with human names
  // Pattern: word_word_word (3+ parts with underscores)
  text = text.replace(/\b(\w+(?:_\w+){2,})\b/g, (match) => humanAgentName(match));

  // Capitalize first letter
  if (text.length > 0) {
    text = text.charAt(0).toUpperCase() + text.slice(1);
  }

  // Clean up double spaces and trailing punctuation
  text = text.replace(/\s{2,}/g, ' ').replace(/[,;]\s*$/, '').trim();

  return text || raw;
}

// Short display name for compact views (circles, inline labels)
function shortAgentName(raw) {
  if (!raw) return '?';
  if (raw === 'Composer') return 'Composer';
  if (raw === 'Orchestrator') return 'Orchestrator';
  if (raw.startsWith('Team:')) return raw.slice(5);
  const human = humanAgentName(raw);
  // Take first two meaningful words, max ~16 chars
  const words = human.split(/\s+/).slice(0, 2).join(' ');
  return words.length > 16 ? words.slice(0, 15) + '…' : words;
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

function IdBadge({ label, value, color = 'text-zinc-600' }) {
  if (!value) return null;
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-mono ${color} bg-zinc-800/60 px-1.5 py-0.5 rounded`}>
      <Hash className="w-2.5 h-2.5" />{label}:{typeof value === 'string' ? value.slice(0, 8) : value}
    </span>
  );
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
  // Composer-level phases
  if (t.includes('composer') && (t.includes('analyzing') || t.includes('goal')))  return { Icon: Crown, color: 'text-amber-300' };
  if (t.includes('designing org') || t.includes('organization'))                   return { Icon: GitBranch, color: 'text-amber-300' };
  if (t.includes('launching team') || t.includes('team'))                          return { Icon: Users, color: 'text-violet-400' };
  if (t.includes('evaluating') && t.includes('team'))                              return { Icon: CheckCircle, color: 'text-amber-300' };
  if (t.includes('gap') && t.includes('team'))                                     return { Icon: Zap, color: 'text-amber-400' };
  if (t.includes('final synthesis') || t.includes('synthesizing'))                 return { Icon: Sparkles, color: 'text-amber-300' };
  // Orchestrator-level phases (legacy)
  if (t.includes('pre-screening') || t.includes('dependencies'))  return { Icon: Zap,       color: 'text-violet-400' };
  if (t.includes('mcts') || t.includes('reasoning'))              return { Icon: Sparkles,   color: 'text-violet-400' };
  if (t.includes('decomposing') || t.includes('assigning'))       return { Icon: Network,    color: 'text-violet-400' };
  if (t.includes('synthesiz'))                                     return { Icon: FileText,   color: 'text-violet-400' };
  if (t.includes('evaluating') || t.includes('metacog'))          return { Icon: CheckCircle, color: 'text-violet-400' };
  // Team-level phases
  if (t.includes('planning') && t.includes('sub-agent'))          return { Icon: Users,      color: 'text-blue-400' };
  if (t.includes('sub-agents') && t.includes('executing'))        return { Icon: Cpu,        color: 'text-blue-400' };
  if (t.includes('delivered') || t.includes('aggregat'))          return { Icon: CheckCircle, color: 'text-emerald-400' };
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
  const isDone = /complet|synthes|found|written|delivered/i.test(text);
  const spinning = Icon === Loader2 && !isDone;
  const displayName = humanAgentName(agent);
  const displayText = humanProgressText(text, agent);

  return (
    <div className="flex items-start gap-2 py-0.5 max-w-2xl">
      <div className={`shrink-0 mt-0.5 ${color}`}>
        {isDone
          ? <CheckCircle className="w-3.5 h-3.5" />
          : <Icon className={`w-3.5 h-3.5 ${spinning ? 'animate-spin' : ''}`} />}
      </div>
      <div className="flex items-baseline gap-1.5 min-w-0">
        {agent && (
          <span className={`text-[11px] font-semibold shrink-0 ${agentColor(agent)}`}>{displayName}</span>
        )}
        <span className="text-xs text-zinc-500 leading-relaxed truncate">{displayText}</span>
      </div>
    </div>
  );
}

// Parse "AgentA → AgentB: message" into {from, to, msg} or null
function parseCollab(text) {
  const m = text.match(/^(.+?)\s*→\s*(.+?):\s*(.+)$/);
  if (!m) return null;
  return { from: m[1].trim(), to: m[2].trim(), msg: m[3].trim() };
}

// ─── Agent Circle (compact animated avatar) ─────────────────────────────────

function AgentCircle({ name, status, role, size = 'md', onClick }) {
  const isActive = status === 'working' || status === 'in_progress';
  const sizeClass = size === 'sm' ? 'w-8 h-8' : size === 'lg' ? 'w-12 h-12' : 'w-10 h-10';
  const iconSize = size === 'sm' ? 'w-3.5 h-3.5' : size === 'lg' ? 'w-5 h-5' : 'w-4 h-4';
  const isComposer = name?.toLowerCase().includes('composer');

  return (
    <button onClick={onClick} className="group flex flex-col items-center gap-1 cursor-pointer" title={`${humanAgentName(name)}\n${role || ''}\n${status}`}>
      <div className={`relative ${sizeClass} rounded-full flex items-center justify-center transition-all
        ${isActive ? 'bg-zinc-800 ring-2 ring-emerald-500/40 shadow-lg shadow-emerald-500/10' : 'bg-zinc-800/80 ring-1 ring-zinc-700'}
        group-hover:ring-zinc-500`}>
        {isComposer
          ? <Crown className={`${iconSize} text-amber-300`} />
          : <Cpu className={`${iconSize} ${agentColor(name)}`} />
        }
        {isActive && (
          <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-400 border-2 border-zinc-900 animate-pulse" />
        )}
      </div>
      <span className={`text-[9px] max-w-[60px] truncate text-center leading-tight ${isActive ? 'text-zinc-300' : 'text-zinc-600'}`}>
        {shortAgentName(name)}
      </span>
    </button>
  );
}

// ─── Communication Line (shows agent → agent messaging) ─────────────────────

function CommLine({ from, to, message, timestamp }) {
  return (
    <div className="flex items-center gap-2 py-1 px-3 text-[11px]">
      <span className={`font-semibold shrink-0 ${agentColor(from)}`}>{shortAgentName(from)}</span>
      <ArrowRight className="w-3 h-3 text-zinc-700 shrink-0" />
      <span className={`font-semibold shrink-0 ${agentColor(to)}`}>{shortAgentName(to)}</span>
      <span className="text-zinc-600 truncate flex-1">{message}</span>
      {timestamp && <span className="text-zinc-700 font-mono shrink-0">{timeAgo(timestamp)}</span>}
    </div>
  );
}

// ─── Live Swarm Section (rendered inline in chat) ──────────────────────────────

function LiveSwarmSection({ liveProgress, teams, roster }) {
  const entries = Object.entries(liveProgress).filter(([, text]) => text && !text.startsWith('__team_event__'));
  if (entries.length === 0) return null;

  // Group entries by team
  const teamGroups = {};  // teamName → [{agent, text}]
  const ungrouped = [];
  const comms = [];       // inter-agent communications

  for (const [agent, text] of entries) {
    const collab = parseCollab(text);
    if (collab) {
      comms.push({ from: collab.from, to: collab.to, msg: collab.msg });
    }

    // Detect team from agent name or from teams state
    const agentTeam = parseAgentTeam(agent);
    const teamFromPrefix = agent.startsWith('Team:') ? agent.slice(5) : null;
    const teamName = teamFromPrefix || agentTeam;

    if (teamName) {
      if (!teamGroups[teamName]) teamGroups[teamName] = [];
      teamGroups[teamName].push({ agent, text });
    } else {
      ungrouped.push({ agent, text });
    }
  }

  const hasTeams = Object.keys(teamGroups).length > 0;

  return (
    <div className="space-y-2 py-1 max-w-2xl">
      {/* Team-grouped activity */}
      {hasTeams && Object.entries(teamGroups).map(([teamName, members]) => {
        const colors = teamColorSet(teamName);
        return (
          <div key={teamName} className={`rounded-lg border ${colors.border} ${colors.bg} px-3 py-2 space-y-1`}>
            <div className="flex items-center gap-2 mb-1">
              <Users className={`w-3 h-3 ${colors.text}`} />
              <span className={`text-[10px] font-semibold ${colors.text}`}>{teamName}</span>
              <span className="text-[10px] text-zinc-600">{members.length} active</span>
            </div>
            {members.map(({ agent, text }) => {
              const { Icon, color } = progressMeta(text, agent);
              const spinning = Icon === Loader2;
              const displayName = agent.startsWith('Team:') ? 'Lead' : shortAgentName(agent);
              const displayText = humanProgressText(text, agent);
              return (
                <div key={agent} className="flex items-start gap-2 py-0.5 ml-2">
                  <Icon className={`w-3 h-3 shrink-0 mt-0.5 ${color} ${spinning ? 'animate-spin' : ''}`} />
                  <span className={`text-[10px] font-semibold shrink-0 ${agentColor(agent)}`}>{displayName}</span>
                  <span className="text-[10px] text-zinc-500 truncate">{displayText}</span>
                </div>
              );
            })}
          </div>
        );
      })}

      {/* Inter-agent communications */}
      {comms.length > 0 && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-2 py-1">
          {comms.map((c, i) => (
            <CommLine key={i} from={c.from} to={c.to} message={c.msg} />
          ))}
        </div>
      )}

      {/* Ungrouped agents (Composer, legacy orchestrator, etc.) */}
      {ungrouped.map(({ agent, text }) => {
        const { Icon, color } = progressMeta(text, agent);
        const isDone = /complet|synthes|delivered/i.test(text);
        const spinning = Icon === Loader2 && !isDone;
        const isComposer = agent?.toLowerCase().includes('composer');
        const displayName = humanAgentName(agent);
        const displayText = humanProgressText(text, agent);
        return (
          <div key={agent} className={`flex items-start gap-2 py-0.5 ${isComposer ? 'pl-1' : ''}`}>
            <div className={`shrink-0 mt-0.5 ${color}`}>
              {isDone
                ? <CheckCircle className="w-3.5 h-3.5" />
                : <Icon className={`w-3.5 h-3.5 ${spinning ? 'animate-spin' : ''}`} />}
            </div>
            <div className="flex items-baseline gap-1.5 min-w-0">
              {isComposer && <Crown className="w-3 h-3 text-amber-300 shrink-0" />}
              <span className={`text-[11px] font-semibold shrink-0 ${agentColor(agent)}`}>{displayName}</span>
              <span className="text-xs text-zinc-500 leading-relaxed truncate">{displayText}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Swarm View (visual org hierarchy) ───────────────────────────────────────

function SwarmView({ teams, roster, liveProgress, activeProjectId, onInspect }) {
  const agents = Object.values(roster);
  const projectAgents = activeProjectId
    ? agents.filter(a => !a.project_id || a.project_id === activeProjectId)
    : agents;

  // Build team → agents mapping
  const teamMap = {};  // teamName → { agents: [], status, id }
  const composerAgent = projectAgents.find(a => a.name?.toLowerCase().includes('composer'));
  const unaffiliated = [];

  for (const agent of projectAgents) {
    if (agent.name?.toLowerCase().includes('composer')) continue;
    const teamName = parseAgentTeam(agent.name) || agent.team_id || null;
    if (teamName) {
      if (!teamMap[teamName]) teamMap[teamName] = { agents: [], status: 'idle', id: teamName };
      teamMap[teamName].agents.push(agent);
      if (agent.status === 'working' || agent.status === 'in_progress') teamMap[teamName].status = 'executing';
    } else {
      unaffiliated.push(agent);
    }
  }

  // Also populate from teams state
  for (const team of teams) {
    const name = team.team_name || team.name || team.id;
    if (!teamMap[name]) teamMap[name] = { agents: [], status: team.status || 'idle', id: team.team_id || team.id };
    teamMap[name].status = team.status || teamMap[name].status;
    if (team.sub_agents) {
      for (const sa of team.sub_agents) {
        if (!teamMap[name].agents.find(a => a.name === sa.name)) {
          teamMap[name].agents.push({ name: sa.name, status: sa.status, role: sa.role });
        }
      }
    }
  }

  // Recent communications from live progress
  const recentComms = [];
  for (const [agent, text] of Object.entries(liveProgress)) {
    if (!text) continue;
    const collab = parseCollab(text);
    if (collab) recentComms.push({ from: collab.from, to: collab.to, msg: collab.msg, ts: Date.now() / 1000 });
  }

  const teamEntries = Object.entries(teamMap);
  const hasAnyActivity = projectAgents.some(a => a.status === 'working' || a.status === 'in_progress');

  if (projectAgents.length === 0 && teams.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center flex-1 text-center gap-3">
        <Network className="w-8 h-8 text-zinc-700" />
        <p className="text-sm text-zinc-500">No swarm deployed yet.</p>
        <p className="text-xs text-zinc-700">Send a message to activate the Composer.</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-4xl mx-auto space-y-6">

        {/* Composer (CEO) */}
        {composerAgent && (
          <div className="flex flex-col items-center gap-3 pb-4">
            <div className="relative">
              <div className={`w-14 h-14 rounded-full flex items-center justify-center transition-all
                ${composerAgent.status === 'working' ? 'bg-amber-500/10 ring-2 ring-amber-400/40 shadow-lg shadow-amber-500/20' : 'bg-zinc-800 ring-1 ring-zinc-700'}`}>
                <Crown className="w-6 h-6 text-amber-300" />
              </div>
              {composerAgent.status === 'working' && (
                <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-amber-400 border-2 border-zinc-950 animate-pulse" />
              )}
            </div>
            <div className="text-center">
              <p className="text-sm font-semibold text-amber-300">Composer</p>
              <p className="text-[10px] text-zinc-600">CEO · Orchestrates all teams</p>
            </div>
            {liveProgress['Composer'] && (
              <p className="text-[11px] text-zinc-500 text-center max-w-md">{humanProgressText(liveProgress['Composer'], 'Composer')}</p>
            )}
            {/* Vertical connector line */}
            {teamEntries.length > 0 && (
              <div className="w-px h-6 bg-zinc-800" />
            )}
          </div>
        )}

        {/* Teams grid */}
        {teamEntries.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {teamEntries.map(([teamName, teamData]) => {
              const colors = teamColorSet(teamName);
              const activeCount = teamData.agents.filter(a => a.status === 'working' || a.status === 'in_progress').length;
              const teamProgress = liveProgress[`Team:${teamName}`];

              return (
                <div key={teamName} className={`rounded-xl border ${colors.border} ${colors.bg} p-4 transition-all
                  ${activeCount > 0 ? 'shadow-lg' : ''}`}>
                  {/* Team header */}
                  <div className="flex items-center gap-2 mb-3">
                    <Users className={`w-4 h-4 ${colors.text}`} />
                    <span className={`text-sm font-semibold ${colors.text}`}>{teamName}</span>
                    <span className="ml-auto text-[10px] text-zinc-600">
                      {teamData.agents.length} agent{teamData.agents.length !== 1 ? 's' : ''}
                    </span>
                    {activeCount > 0 && (
                      <span className={`text-[10px] ${colors.text}`}>{activeCount} active</span>
                    )}
                  </div>

                  {/* Team status */}
                  {teamProgress && (
                    <p className="text-[10px] text-zinc-500 mb-3 truncate">{humanProgressText(teamProgress, `Team:${teamName}`)}</p>
                  )}

                  {/* Agent circles row */}
                  <div className="flex flex-wrap gap-3 justify-center">
                    {teamData.agents.map(agent => (
                      <AgentCircle
                        key={agent.name}
                        name={agent.name}
                        status={agent.status}
                        role={agent.role || agentRoleHint(agent.name)}
                        size="sm"
                        onClick={() => onInspect(agent.name)}
                      />
                    ))}
                  </div>

                  {/* Team ID */}
                  <div className="mt-3 flex items-center gap-2">
                    <IdBadge label="team" value={teamData.id} color={colors.text} />
                    <StatusDot status={teamData.status || (activeCount > 0 ? 'working' : 'idle')} />
                    <span className={`text-[10px] ${STATUS_TEXT[teamData.status] || 'text-zinc-600'}`}>
                      {teamData.status || (activeCount > 0 ? 'executing' : 'idle')}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Unaffiliated agents */}
        {unaffiliated.length > 0 && (
          <section>
            <p className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider mb-3">
              Standalone Agents · {unaffiliated.length}
            </p>
            <div className="flex flex-wrap gap-3">
              {unaffiliated.map(agent => (
                <AgentCircle
                  key={agent.name}
                  name={agent.name}
                  status={agent.status}
                  size="md"
                  onClick={() => onInspect(agent.name)}
                />
              ))}
            </div>
          </section>
        )}

        {/* Recent inter-agent communications */}
        {recentComms.length > 0 && (
          <section>
            <p className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider mb-2">
              Live Communications
            </p>
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 divide-y divide-zinc-800/40">
              {recentComms.slice(0, 10).map((c, i) => (
                <CommLine key={i} from={c.from} to={c.to} message={c.msg} timestamp={c.ts} />
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

// ─── Right Panel ───────────────────────────────────────────────────────────────

function RightPanel({ projectTasks, isOpen, onToggle, sessionId, activeProjectId }) {
  if (!isOpen) {
    return (
      <button onClick={onToggle}
        className="w-8 flex flex-col items-center py-4 border-l border-zinc-800 text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/30 transition-colors cursor-pointer shrink-0"
        title="Show tasks">
        <ChevronLeft className="w-3.5 h-3.5" />
      </button>
    );
  }

  const tasks = [...projectTasks]
    .sort((a, b) => (b.updated_at || b.created_at || 0) - (a.updated_at || a.created_at || 0))
    .slice(0, 20);

  const active = tasks.filter(t => ['in_progress', 'pending'].includes(t.status));
  const done   = tasks.filter(t => !['in_progress', 'pending'].includes(t.status));

  return (
    <aside className="w-60 flex flex-col border-l border-zinc-800 shrink-0 overflow-hidden">
      <div className="h-12 flex items-center justify-between px-4 border-b border-zinc-800 shrink-0">
        <span className="text-xs font-medium text-zinc-400">Tasks</span>
        {active.length > 0 && (
          <span className="text-[10px] text-emerald-500 font-mono">{active.length} running</span>
        )}
        <button onClick={onToggle}
          className="w-6 h-6 flex items-center justify-center text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800 rounded transition-all cursor-pointer ml-auto">
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Session & Project IDs */}
      <div className="px-3 py-2 border-b border-zinc-800/60 flex flex-wrap gap-1">
        <IdBadge label="session" value={sessionId} />
        <IdBadge label="project" value={activeProjectId} />
      </div>

      <div className="flex-1 overflow-y-auto py-2">
        {tasks.length === 0 ? (
          <p className="text-xs text-zinc-700 px-4 py-3">No tasks yet.</p>
        ) : (
          <div>
            {active.map(t => (
              <div key={t.id} className="px-4 py-2.5 border-b border-zinc-800/40 hover:bg-zinc-800/20 transition-colors">
                <div className="flex items-center gap-2 mb-1">
                  <StatusDot status={t.status} />
                  {t.assigned_to
                    ? <span className={`text-[10px] font-semibold ${agentColor(t.assigned_to)}`}>{humanAgentName(t.assigned_to)}</span>
                    : <span className="text-[10px] text-zinc-600">Unassigned</span>
                  }
                  <span className="text-[10px] text-zinc-700 ml-auto font-mono">{timeAgo(t.updated_at || t.created_at)}</span>
                </div>
                <p className="text-[11px] text-zinc-400 leading-relaxed line-clamp-2">{t.description}</p>
              </div>
            ))}
            {done.length > 0 && (
              <>
                {active.length > 0 && <div className="mx-4 my-1 border-t border-zinc-800/60" />}
                {done.map(t => (
                  <div key={t.id} className="px-4 py-2 hover:bg-zinc-800/10 transition-colors">
                    <div className="flex items-center gap-2 mb-0.5">
                      <StatusDot status={t.status} />
                      {t.assigned_to && (
                        <span className={`text-[10px] ${agentColor(t.assigned_to)} opacity-50`}>{humanAgentName(t.assigned_to)}</span>
                      )}
                      <span className="text-[10px] text-zinc-700 ml-auto font-mono">{timeAgo(t.updated_at || t.created_at)}</span>
                    </div>
                    <p className="text-[10px] text-zinc-600 leading-relaxed line-clamp-1">{t.description}</p>
                  </div>
                ))}
              </>
            )}
          </div>
        )}
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

function AssistantMessage({ text }) {
  return (
    <div className="flex items-start gap-2.5 pt-1">
      <div className="w-5 h-5 rounded-md bg-zinc-800 border border-zinc-700 flex items-center justify-center shrink-0 mt-0.5">
        <Bot className="w-3 h-3 text-zinc-400" />
      </div>
      <div className="flex-1 min-w-0 text-sm text-zinc-200 leading-relaxed space-y-1.5">
        {text.split('\n').map((line, j) => {
          if (line.startsWith('### ')) return <p key={j} className="font-semibold text-zinc-100 mt-2">{line.slice(4)}</p>;
          if (line.startsWith('## '))  return <p key={j} className="font-semibold text-zinc-100 text-base mt-3">{line.slice(3)}</p>;
          if (line.startsWith('# '))   return <p key={j} className="font-bold text-zinc-100 text-lg mt-3">{line.slice(2)}</p>;
          if (line.startsWith('- ') || line.startsWith('* ')) return <p key={j} className="pl-3 text-zinc-300">· {line.slice(2)}</p>;
          return <p key={j} className={line === '' ? 'mt-1' : ''}>{line || '\u00A0'}</p>;
        })}
      </div>
    </div>
  );
}

function ChatView({ messages, isTyping, input, setInput, sendMessage, activeProject, connected, projectAgents, liveProgress, onSteer, teams, roster }) {
  const endRef      = useRef(null);
  const textareaRef = useRef(null);

  const liveEntries = Object.entries(liveProgress).filter(([, text]) => text && !text.startsWith('__team_event__'));
  const isSwarmActive = liveEntries.length > 0 || projectAgents.some(a => a.status === 'working');

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, liveEntries.length, isTyping]);

  const onChange = (e) => {
    setInput(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px';
  };

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto px-6 py-8 space-y-3">

          {messages.length === 0 && liveEntries.length === 0 && !isTyping && (
            <div className="flex flex-col items-center justify-center py-24 text-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-center">
                <Crown className="w-5 h-5 text-amber-300/40" />
              </div>
              <div>
                <p className="text-sm font-medium text-zinc-300">
                  {activeProject ? activeProject.name : 'No chat selected'}
                </p>
                <p className="text-sm text-zinc-600 mt-1">
                  {activeProject ? 'Send a message to deploy the Composer and agent swarm.' : 'Select or create a chat to begin.'}
                </p>
              </div>
            </div>
          )}

          {messages.map((m, i) => {
            if (m.role === 'progress') return <ActivityLine key={i} text={m.text} agent={m.agent} />;
            if (m.role === 'user') return (
              <div key={i} className="flex justify-end pt-1">
                <div className="max-w-[72%] bg-zinc-800 text-zinc-100 px-4 py-2.5 rounded-2xl rounded-tr-sm text-sm leading-relaxed">
                  {m.text.split('\n').map((line, j) => (
                    <p key={j} className={j > 0 ? 'mt-1.5' : ''}>{line || '\u00A0'}</p>
                  ))}
                </div>
              </div>
            );
            if (m.role === 'system') return (
              <div key={i} className="flex items-start gap-2.5 pt-1">
                <div className="w-5 h-5 rounded-md bg-red-500/10 flex items-center justify-center shrink-0 mt-0.5">
                  <Activity className="w-3 h-3 text-red-400" />
                </div>
                <p className="text-sm text-red-400/80 leading-relaxed">{m.text}</p>
              </div>
            );
            return <AssistantMessage key={i} text={m.text} />;
          })}

          {liveEntries.length > 0 && (
            <LiveSwarmSection liveProgress={liveProgress} teams={teams} roster={roster} />
          )}

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

      <div className="px-6 pb-6 pt-2">
        <div className="max-w-2xl mx-auto space-y-2">
          {isSwarmActive && <InjectBar onSteer={onSteer} />}
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
                  isSwarmActive ? 'Swarm running — queue a follow-up...' : 'Message...'
                }
                disabled={!activeProject || !connected}
                rows={1}
                className="flex-1 bg-transparent px-4 py-3 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none resize-none"
                style={{ minHeight: '46px', maxHeight: '160px' }}
              />
              <button type="submit"
                disabled={!input.trim() || !activeProject || !connected}
                className="m-1.5 h-8 w-8 bg-zinc-700 hover:bg-zinc-600 disabled:opacity-30 disabled:cursor-not-allowed rounded-lg transition-colors flex items-center justify-center shrink-0 cursor-pointer">
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
  if (n.includes('composer'))     return 'Composer (CEO)';
  if (n.includes('orchestrat'))   return 'Orchestrator';
  if (n.includes('research'))     return 'Research';
  if (n.includes('analyst'))      return 'Analysis';
  if (n.includes('writer'))       return 'Writing';
  if (n.includes('develop'))      return 'Development';
  if (n.includes('design'))       return 'Design';
  if (n.includes('legal'))        return 'Legal';
  if (n.includes('market'))       return 'Marketing';
  if (n.includes('strateg'))      return 'Strategy';
  if (n.includes('specialist')) {
    const parts = name.split('_').slice(1, -1);
    if (parts.length) return parts.join(' ');
  }
  return 'Specialist';
}

function AgentsView({ roster, activeProjectId, onInspect, wsAction, teams }) {
  const [viewMode, setViewMode] = useState('team'); // 'team' | 'flat'
  const agents = Object.values(roster);
  const shown = activeProjectId
    ? agents.filter(a => !a.project_id || a.project_id === activeProjectId)
    : agents;

  if (shown.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center flex-1 text-center gap-3">
        <Cpu className="w-8 h-8 text-zinc-700" />
        <p className="text-sm text-zinc-500">No agents deployed yet.</p>
        <p className="text-xs text-zinc-700">Send a message to start the swarm.</p>
      </div>
    );
  }

  // Group by team
  const teamGroups = {};  // teamName → agents[]
  const noTeam = [];
  for (const agent of shown) {
    const teamName = parseAgentTeam(agent.name) || agent.team_id;
    if (teamName) {
      if (!teamGroups[teamName]) teamGroups[teamName] = [];
      teamGroups[teamName].push(agent);
    } else {
      noTeam.push(agent);
    }
  }

  const renderAgentCard = (agent) => {
    const isActive = agent.status === 'working' || agent.status === 'in_progress';
    return (
      <div key={agent.name}
        className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 group hover:border-zinc-700 transition-colors">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="relative shrink-0">
              <div className="w-8 h-8 rounded-lg bg-zinc-800 flex items-center justify-center">
                {agent.name?.toLowerCase().includes('composer')
                  ? <Crown className="w-4 h-4 text-amber-300" />
                  : <Cpu className={`w-4 h-4 ${agentColor(agent.name)}`} />
                }
              </div>
              {isActive && (
                <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-400 border-2 border-zinc-900 animate-pulse" />
              )}
            </div>
            <div className="min-w-0">
              <p className={`text-sm font-medium ${agentColor(agent.name)} truncate`}>{humanAgentName(agent.name)}</p>
              <p className="text-[11px] text-zinc-600">{agentRoleHint(agent.name)}</p>
            </div>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button onClick={() => onInspect(agent.name)}
              className="flex items-center gap-1 px-2 py-1 text-[11px] text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 rounded-md transition-all cursor-pointer">
              <Eye className="w-3 h-3" /> Inspect
            </button>
            {agent.current_task && isActive && (
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
        <div className="mt-2 flex items-center gap-2">
          <StatusDot status={agent.status || 'idle'} />
          <StatusLabel status={agent.status || 'idle'} />
          <span className="text-[10px] text-zinc-700 font-mono ml-auto">{timeAgo(agent.updated_at)}</span>
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Toolbar */}
      <div className="px-4 py-2.5 border-b border-zinc-800 flex items-center gap-3 shrink-0">
        <div className="flex items-center gap-0.5 bg-zinc-900 rounded-lg p-0.5 border border-zinc-800">
          {[{ key: 'team', label: 'By Team', Icon: Users }, { key: 'flat', label: 'All', Icon: List }].map(v => (
            <button key={v.key} onClick={() => setViewMode(v.key)}
              className={`px-2.5 py-1 rounded-md text-xs transition-colors cursor-pointer flex items-center gap-1.5 ${
                viewMode === v.key ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
              }`}>
              <v.Icon className="w-3 h-3" />
              {v.label}
            </button>
          ))}
        </div>
        <span className="text-[10px] text-zinc-700 font-mono ml-auto">{shown.length} agents</span>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-3xl mx-auto space-y-6">

          {viewMode === 'team' ? (
            <>
              {Object.entries(teamGroups).map(([teamName, teamAgents]) => {
                const colors = teamColorSet(teamName);
                const activeCount = teamAgents.filter(a => a.status === 'working' || a.status === 'in_progress').length;
                return (
                  <section key={teamName}>
                    <div className={`flex items-center gap-2 mb-3 px-3 py-2 rounded-lg ${colors.bg} border ${colors.border}`}>
                      <Users className={`w-4 h-4 ${colors.text}`} />
                      <span className={`text-xs font-semibold ${colors.text}`}>{teamName}</span>
                      <span className="text-[10px] text-zinc-600">
                        {teamAgents.length} agent{teamAgents.length !== 1 ? 's' : ''}
                      </span>
                      {activeCount > 0 && (
                        <span className="text-[10px] text-emerald-500 ml-auto">{activeCount} active</span>
                      )}
                    </div>
                    <div className="space-y-2 ml-2">
                      {teamAgents.map(renderAgentCard)}
                    </div>
                  </section>
                );
              })}
              {noTeam.length > 0 && (
                <section>
                  <p className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider mb-3">
                    {Object.keys(teamGroups).length > 0 ? 'Other Agents' : 'Active'} · {noTeam.length}
                  </p>
                  <div className="space-y-2">
                    {noTeam.map(renderAgentCard)}
                  </div>
                </section>
              )}
            </>
          ) : (
            <>
              {/* Flat view: working first, then idle */}
              {shown.filter(a => a.status === 'working' || a.status === 'in_progress').length > 0 && (
                <section>
                  <p className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider mb-3">
                    Active · {shown.filter(a => a.status === 'working' || a.status === 'in_progress').length}
                  </p>
                  <div className="space-y-2">
                    {shown.filter(a => a.status === 'working' || a.status === 'in_progress').map(renderAgentCard)}
                  </div>
                </section>
              )}
              {shown.filter(a => a.status !== 'working' && a.status !== 'in_progress').length > 0 && (
                <section>
                  <p className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider mb-3">
                    Standby · {shown.filter(a => a.status !== 'working' && a.status !== 'in_progress').length}
                  </p>
                  <div className="bg-zinc-900 border border-zinc-800 rounded-xl divide-y divide-zinc-800">
                    {shown.filter(a => a.status !== 'working' && a.status !== 'in_progress').map(agent => (
                      <div key={agent.name}
                        className="flex items-center gap-3 px-4 py-3 group hover:bg-zinc-800/40 transition-colors">
                        <StatusDot status={agent.status || 'idle'} />
                        <div className="flex-1 min-w-0">
                          <span className="text-xs text-zinc-400">{humanAgentName(agent.name)}</span>
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
            </>
          )}
        </div>
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
          <span className="text-[10px] text-zinc-700 font-mono">{task.id?.slice(0, 12)}</span>
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
  const [groupBy, setGroupBy] = useState('agent');
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

  const renderByAgent = () => {
    const groups = {};
    for (const t of scoped) {
      const key = t.assigned_to || 'Unassigned';
      if (!groups[key]) groups[key] = [];
      groups[key].push(t);
    }
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
              {agentName === 'Unassigned' ? agentName : humanAgentName(agentName)}
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
            <span className={`shrink-0 w-32 truncate ${agentColor(log.agent)}`}>[{humanAgentName(log.agent)}]</span>
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
  const teamName = parseAgentTeam(agent);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-8 bg-black/60 backdrop-blur-sm"
      onClick={onClose}>
      <div className="w-full max-w-lg max-h-[80vh] bg-zinc-900 border border-zinc-700/60 rounded-xl overflow-hidden shadow-2xl flex flex-col"
        onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-3">
            <StatusDot status={agentData?.status || 'idle'} size="md" />
            <div>
              <p className={`text-sm font-medium ${agentColor(agent)}`}>{humanAgentName(agent)}</p>
              <div className="flex items-center gap-2 mt-0.5">
                <p className="text-xs text-zinc-500">
                  {agentRoleHint(agent)}
                  {agentData?.status ? ` · ${agentData.status}` : ''}
                </p>
                {teamName && (
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${teamColorSet(teamName).bg} ${teamColorSet(teamName).text}`}>
                    {teamName}
                  </span>
                )}
              </div>
            </div>
          </div>
          <button onClick={onClose}
            className="w-7 h-7 flex items-center justify-center text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 rounded-md transition-all cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* IDs section */}
        <div className="px-5 py-2 border-b border-zinc-800/60 flex flex-wrap gap-2">
          <IdBadge label="agent" value={agent} />
          {teamName && <IdBadge label="team" value={teamName} color={teamColorSet(teamName).text} />}
          {agentData?.project_id && <IdBadge label="project" value={agentData.project_id} />}
        </div>

        <div className="overflow-y-auto flex-1 p-5 space-y-4">
          {agentData?.current_task && (
            <div className="bg-zinc-800/50 rounded-lg p-3">
              <p className="text-[10px] text-zinc-600 uppercase tracking-wider mb-1">Current Task</p>
              <p className="text-xs text-zinc-300 leading-relaxed">{agentData.current_task}</p>
            </div>
          )}
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
  const [menuFor, setMenuFor]       = useState(null);
  const [renaming, setRenaming]     = useState(null);
  const [renameVal, setRenameVal]   = useState('');
  const [confirming, setConfirming] = useState(null);
  const menuRef = useRef(null);

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
                <button
                  onClick={e => { e.stopPropagation(); setMenuFor(menuFor === p.id ? null : p.id); }}
                  className="opacity-0 group-hover:opacity-100 w-5 h-5 flex items-center justify-center text-zinc-500 hover:text-zinc-200 rounded transition-all cursor-pointer shrink-0 mt-0.5"
                  title="Options">
                  <span className="text-base leading-none tracking-widest" style={{ letterSpacing: '-1px' }}>···</span>
                </button>
              </button>
            )}

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
  { key: 'swarm',  label: 'Swarm',  Icon: Network       },
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
  const [teams, setTeams]             = useState([]);
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

  const loadTeams = useCallback(async () => {
    try {
      const r = await fetch('/api/teams');
      if (r.ok) {
        const data = await r.json();
        if (Array.isArray(data)) setTeams(data);
      }
    } catch {}
  }, []);

  useEffect(() => { loadProjects(); }, [loadProjects]);
  useEffect(() => {
    if (activeTab === 'tasks')  loadTasks(activeProjectId);
    if (activeTab === 'agents') loadAgents(activeProjectId);
    if (activeTab === 'swarm')  { loadAgents(activeProjectId); loadTeams(); }
  }, [activeTab, activeProjectId, loadTasks, loadAgents, loadTeams]);

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
        socket.send(JSON.stringify({ type: 'get_teams' }));
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
      case 'teams_init':
        if (Array.isArray(data.teams)) setTeams(data.teams);
        break;
      case 'team_update': {
        // Structured team event from backend
        const teamEvent = data;
        setTeams(prev => {
          const idx = prev.findIndex(t => (t.team_id || t.id) === teamEvent.team_id);
          if (idx >= 0) {
            const next = [...prev];
            next[idx] = { ...next[idx], ...teamEvent };
            return next;
          }
          return [...prev, teamEvent];
        });
        break;
      }
      case 'agent_status':
        setRoster(prev => ({
          ...prev,
          [data.agent]: {
            ...prev[data.agent],
            name: data.agent, status: data.status, current_task: data.task,
            project_id: data.project_id || prev[data.agent]?.project_id || '',
            team_id: data.team_id || prev[data.agent]?.team_id || '',
            updated_at: Date.now() / 1000,
          }
        }));
        // Clear live activity for any terminal status
        if (['idle', 'error', 'done', 'completed', 'failed', 'killed'].includes(data.status)) {
          setLiveProgress(prev => {
            const next = { ...prev };
            delete next[data.agent];
            // Also clear Team:-prefixed entry if this was the last active agent in that team
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

        // Parse structured team events encoded in progress text
        if (text.startsWith('__team_event__')) {
          try {
            const teamPayload = JSON.parse(text.slice('__team_event__'.length));
            setTeams(prev => {
              const idx = prev.findIndex(t => (t.team_id || t.id) === teamPayload.team_id);
              if (idx >= 0) {
                const next = [...prev];
                next[idx] = { ...next[idx], ...teamPayload };
                return next;
              }
              return [...prev, teamPayload];
            });
          } catch {}
          break;
        }

        // Detect if this progress signals completion
        const isDoneSignal = /\b(completed|done|delivered|finished|failed|error|stopped)\b/i.test(text);

        if (isDoneSignal) {
          // Remove from live strip — it's done, don't keep it animating
          setLiveProgress(prev => {
            const next = { ...prev };
            delete next[agent || '_'];
            return next;
          });
        } else {
          // Update the live activity strip (in-place per agent)
          setLiveProgress(prev => ({ ...prev, [agent || '_']: text }));
        }

        // Pin major phase transitions to chat history
        const isComposerPhase = agent === 'Composer' &&
          /analyzing|designing org|launching team|evaluating|gap team|final synthesis|completed/i.test(text);
        const isOrchestratorPhase = agent === 'Orchestrator' &&
          /pre-screening|mcts|decomposing|synthesiz|evaluating|metacog|launching|pipeline ready/i.test(text);
        const isTeamPhase = agent.startsWith('Team:') &&
          /planning|executing|delivered|aggregat|completed|failed/i.test(text);

        if (isComposerPhase || isOrchestratorPhase || isTeamPhase) {
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
          setMessages([]); setLiveProgress({}); setTasks([]); setRoster({}); setTeams([]);
        }
        break;
      case 'project_stopped':
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
        // Final response arrived — clear all live activity since the swarm is done
        setLiveProgress({});
        // Mark all agents as idle since the response is complete
        setRoster(prev => {
          const next = { ...prev };
          Object.keys(next).forEach(name => {
            if (next[name].status === 'working' || next[name].status === 'in_progress') {
              next[name] = { ...next[name], status: 'idle', current_task: '' };
            }
          });
          return next;
        });
        // Mark all teams as done
        setTeams(prev => prev.map(t =>
          (t.status === 'executing' || t.status === 'planning')
            ? { ...t, status: 'done' }
            : t
        ));
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
    setMessages([]); setLiveProgress({}); setTraces({}); setTasks([]); setTelemetry([]); setRoster({}); setTeams([]);
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
  const activeTeams   = teams.filter(t => t.status === 'executing' || t.status === 'planning').length;

  const showRightPanel = activeTab === 'chat';

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-100 overflow-hidden">

      {/* ── Sidebar ── */}
      <aside className="w-52 flex flex-col border-r border-zinc-800 shrink-0">
        <div className="px-4 h-12 flex items-center gap-2.5 border-b border-zinc-800">
          <div className="w-6 h-6 rounded-md bg-zinc-800 border border-zinc-700 flex items-center justify-center">
            <Crown className="w-3.5 h-3.5 text-amber-300" />
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
              const count = key === 'agents' ? (activeAgents || null)
                          : key === 'tasks' ? (activeTasks || null)
                          : key === 'swarm' ? (activeTeams || activeAgents || null)
                          : null;
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
            {sessionId && <IdBadge label="session" value={sessionId} />}
            {activeProject && (
              <span className="text-zinc-400 truncate max-w-[200px]">{activeProject.name}</span>
            )}
            {activeAgents > 0 && (
              <>
                <span className="flex items-center gap-1.5 text-emerald-500">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  {activeAgents} agent{activeAgents !== 1 ? 's' : ''}
                  {activeTeams > 0 ? ` · ${activeTeams} team${activeTeams !== 1 ? 's' : ''}` : ''}
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
                onSteer={injectSteer} teams={teams} roster={roster} />
            )}
            {activeTab === 'swarm' && (
              <SwarmView teams={teams} roster={roster} liveProgress={liveProgress}
                activeProjectId={activeProjectId} onInspect={setInspectAgent} />
            )}
            {activeTab === 'agents' && (
              <AgentsView roster={roster} activeProjectId={activeProjectId}
                onInspect={setInspectAgent} wsAction={wsAction} teams={teams} />
            )}
            {activeTab === 'tasks' && (
              <TasksView tasks={tasks} activeProjectId={activeProjectId} wsAction={wsAction} />
            )}
            {activeTab === 'logs' && <LogsView telemetry={telemetry} />}
          </div>

          {showRightPanel && (
            <RightPanel
              projectTasks={projectTasks}
              isOpen={rightPanelOpen}
              onToggle={() => setRightPanelOpen(o => !o)}
              sessionId={sessionId}
              activeProjectId={activeProjectId}
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
