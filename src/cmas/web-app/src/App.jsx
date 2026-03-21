import React, { useState, useEffect, useRef, useMemo } from 'react';
import { 
  Send as SendIcon, Plus as PlusIcon, Bot as BotIcon, Command as CommandIcon, Activity as ActivityIcon, 
  Database as DatabaseIcon, FileText as FileTextIcon, X as XIcon, ChevronRight as ChevronRightIcon, LayoutGrid as LayoutGridIcon, 
  Terminal as TermIcon, Search as SearchIcon, Info as InfoIcon, Settings as SettingsIcon, User as UserIcon, 
  Globe as GlobeIcon, Zap as ZapIcon, FastForward as FastForwardIcon, Square as SquareIcon, Layers as LayersIcon, MessageSquare as MessageSquareIcon,
  Cpu as CpuIcon, Hash as HashIcon, Link as LinkIcon, Eye as EyeIcon, Clipboard as ClipboardIcon, List as ListIcon, MoreHorizontal as MoreHorizontalIcon,
  FolderOpen as FolderOpenIcon, ArrowUpRight as ArrowUpRightIcon, Share2 as Share2Icon, Sparkles as SparklesIcon, Archive as ArchiveIcon, Lock as LockIcon
} from 'lucide-react';

export default function App() {
  const [ws, setWs] = useState(null);
  const [activeProjectId, setActiveProjectId] = useState(localStorage.getItem('cmas_project_id') || '');
  const [sessionId, setSessionId] = useState(localStorage.getItem('cmas_session_id') || '');
  const [projects, setProjects] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [messages, setMessages] = useState([]);
  const [roster, setRoster] = useState({});
  const [telemetry, setTelemetry] = useState([]);
  const [traces, setTraces] = useState({});
  const [comms, setComms] = useState([]); // Agent-to-Agent links
  const [input, setInput] = useState('');
  const [connected, setConnected] = useState(false);
  const [activeTab, setActiveTab] = useState('chat'); // 'chat' | 'swarm' | 'files'
  const [fileTree, setFileTree] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileContent, setFileContent] = useState(null);
  const [isLoadingFile, setIsLoadingFile] = useState(false);
  const [inspectAgent, setInspectAgent] = useState(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isAssetDrawerOpen, setIsAssetDrawerOpen] = useState(false);

  const messagesEndRef = useRef(null);
  const telemetryEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // APIs
  const loadProjects = async () => {
    try {
      const res = await fetch(`http://${window.location.host}/api/projects`);
      if (res.ok) setProjects(await res.json());
    } catch (e) { console.error("Projects error", e); }
  };

  const loadFileTree = async () => {
    try {
      const res = await fetch(`http://${window.location.host}/api/workspace`);
      if (res.ok) setFileTree(await res.json());
    } catch (e) { console.error("Workspace error", e); }
  };

  const loadFileContent = async (path) => {
    setIsLoadingFile(true);
    setSelectedFile(path);
    try {
      const res = await fetch(`http://${window.location.host}/api/workspace/file?path=${encodeURIComponent(path)}`);
      if (res.ok) setFileContent((await res.json()).content);
    } catch (e) { setFileContent("// Error loading"); }
    finally { setIsLoadingFile(false); }
  };

  useEffect(() => { loadProjects(); loadFileTree(); }, []);

  // WebSocket
  useEffect(() => {
    let socket = null;
    let reconnectTimeout = null;

    const connect = () => {
      const url = `ws://${window.location.host}/ws?session_id=${sessionId}&user_id=web_user&project_id=${activeProjectId}`;
      socket = new WebSocket(url);

      socket.onopen = () => {
        setConnected(true);
        socket.send(JSON.stringify({ type: 'get_sessions' }));
        if (sessionId) socket.send(JSON.stringify({ type: 'get_history' }));
      };

      socket.onclose = () => {
        setConnected(false);
        reconnectTimeout = setTimeout(connect, 3000);
      };

      socket.onmessage = (e) => {
        const data = JSON.parse(e.data);
        handleMessage(data);
      };

      setWs(socket);
    };

    connect();
    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (socket) socket.close();
    };
  }, [sessionId, activeProjectId]);

  const handleMessage = (data) => {
    switch (data.type) {
      case 'session':
        if (!sessionId) {
          setSessionId(data.session_id);
          localStorage.setItem('cmas_session_id', data.session_id);
        }
        break;
      case 'session_list':
        setSessions(data.sessions || []);
        break;
      case 'history':
        setMessages((data.messages || []).map(m => ({ role: m.role, text: m.content })));
        break;
      case 'roster_init':
        const r = {};
        (data.agents || []).forEach(a => { r[a.name] = a; });
        setRoster(r);
        break;
      case 'agent_status':
        setRoster(prev => ({
          ...prev,
          [data.agent]: { ...prev[data.agent], name: data.agent, status: data.status, current_task: data.task }
        }));
        break;
      case 'trace':
        setTraces(prev => ({
          ...prev,
          [data.agent]: [{ type: data.step_type, content: data.content, ts: data.ts }, ...(prev[data.agent] || [])].slice(0, 30)
        }));
        setTelemetry(prev => [{ ...data, id: Date.now() + Math.random() }, ...prev].slice(0, 50));
        break;
      case 'comm':
        setComms(prev => [{ ...data, id: Date.now() + Math.random() }, ...prev].slice(0, 10));
        break;
      case 'message':
      case 'proactive':
      case 'error':
        setMessages(prev => [...prev, { role: data.type === 'error' ? 'system' : 'assistant', text: data.text }]);
        break;
    }
  };

  const sendMessage = (type = 'chat', customText = null) => {
    const text = customText !== null ? customText : input.trim();
    if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
    if (type !== 'steer') setMessages(prev => [...prev, { role: 'user', text }]);
    ws.send(JSON.stringify({ type, text, project_id: activeProjectId }));
    if (customText === null) setInput('');
  };

  const createNewProject = () => {
    const name = prompt("Mission Name (e.g. Neo-Luddite Risk Assessment):");
    if (!name) return;
    ws.send(JSON.stringify({ type: 'create_project', name, focus: 'Primary Mission' }));
    setTimeout(loadProjects, 500);
  };

  const createNewSession = () => {
    localStorage.removeItem('cmas_session_id');
    setSessionId('');
    setMessages([]);
    setTraces({});
  };

  const selectProject = (pid) => {
    setActiveProjectId(pid);
    localStorage.setItem('cmas_project_id', pid);
    setSessionId('');
    setMessages([]);
    setRoster({});
    setTraces({});
    loadProjects();
  };

  // Swarm Interaction Map logic
  const agentPositions = useMemo(() => {
    const names = Object.keys(roster);
    const pos = {};
    names.forEach((name, i) => {
      const angle = (i / names.length) * 2 * Math.PI;
      pos[name] = { x: 50 + 35 * Math.cos(angle), y: 50 + 35 * Math.sin(angle) };
    });
    return pos;
  }, [roster]);

  const renderFileNode = (node, depth = 0) => (
    <div key={node.path} style={{ paddingLeft: `${depth * 12}px` }}>
      <div 
        onClick={() => node.type === 'file' ? loadFileContent(node.path) : null}
        className={`flex items-center gap-2 p-1.5 hover:bg-white/5 rounded-md cursor-pointer transition-all ${selectedFile === node.path ? 'bg-blue-600/20 text-blue-400 font-bold' : 'text-slate-500'}`}
      >
        {node.type === 'directory' ? <LayersIcon className="w-3.5 h-3.5 opacity-40" /> : <DatabaseIcon className="w-3.5 h-3.5 opacity-40" />}
        <span className="text-[11px] truncate uppercase tracking-tight font-black">{node.name}</span>
      </div>
      {node.children && node.children.map(child => renderFileNode(child, depth + 1))}
    </div>
  );

  return (
    <div className="flex h-screen bg-[#050505] text-slate-100 overflow-hidden font-sans selection:bg-blue-500/30">
      
      {/* ── Minimalist Sidebar ────────────────────────────────────── */}
      <aside className={`flex flex-col border-r border-white/5 bg-[#0a0a0b] transition-all duration-500 ease-in-out ${isSidebarOpen ? 'w-80' : 'w-0 overflow-hidden opacity-0 shadow-none'}`}>
        <div className="p-8 border-b border-white/5">
           <div className="flex items-center gap-4 mb-8">
              <div className="w-12 h-12 rounded-[22px] bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center shadow-[0_10px_30px_rgba(37,99,235,0.2)] rotate-2">
                <SparklesIcon className="w-7 h-7 text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <h1 className="text-xl font-black tracking-tighter text-white uppercase italic leading-none truncate">CMAS <span className="text-blue-500">Core</span></h1>
                <div className="flex items-center gap-2 mt-1">
                   <div className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`} />
                   <span className="text-[10px] text-slate-500 uppercase font-black tracking-widest">{connected ? 'Live Swarm' : 'No Signal'}</span>
                </div>
              </div>
           </div>
           
           <button 
             onClick={createNewSession}
             className="w-full py-4 bg-white/5 hover:bg-white/10 rounded-2xl border border-white/5 flex items-center justify-center gap-3 transition-all group"
           >
              <PlusIcon className="w-5 h-5 text-slate-400 group-hover:text-blue-400 transition-colors" />
              <span className="text-[13px] font-black uppercase tracking-widest text-slate-400">New Mission</span>
           </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-8 space-y-10 custom-scrollbar">
           <div>
              <div className="flex items-center justify-between mb-4 px-2">
                <span className="text-[10px] font-black text-slate-700 uppercase tracking-[0.2em] italic">Intelligence Clusters</span>
                <button onClick={createNewProject} className="text-blue-500 p-1 rounded-lg"><PlusIcon className="w-4 h-4" /></button>
              </div>
              <div className="space-y-1.5">
                 {projects.map(p => (
                   <button 
                     key={p.id} onClick={() => selectProject(p.id)}
                     className={`w-full text-left px-5 py-4 rounded-3xl text-xs transition-all border ${p.id === activeProjectId ? 'bg-blue-600 text-white shadow-2xl shadow-blue-900/30' : 'border-transparent text-slate-400 hover:bg-white/5'}`}
                   >
                     <div className="font-black uppercase tracking-tight text-[12px] truncate">{p.name}</div>
                     <div className={`text-[9px] font-bold uppercase tracking-widest mt-1 opacity-50 ${p.id === activeProjectId ? 'text-blue-200' : 'text-slate-600'}`}>{p.focus || 'Cluster v5.9'}</div>
                   </button>
                 ))}
              </div>
           </div>

           <div>
              <div className="flex items-center justify-between mb-4 px-2">
                <span className="text-[10px] font-black text-slate-700 uppercase tracking-[0.2em] italic">Session Logs</span>
              </div>
              <div className="space-y-1">
                 {sessions.map(s => (
                   <button 
                     key={s.id} onClick={() => { setSessionId(s.id); localStorage.setItem('cmas_session_id', s.id); setMessages([]); }}
                     className={`w-full text-left p-3 rounded-2xl text-[11px] transition-all border ${s.id === sessionId ? 'bg-slate-900 border-white/10 text-slate-200' : 'border-transparent text-slate-600 hover:text-slate-400'}`}
                   >
                     <div className="truncate font-bold italic tracking-tight">{s.summary || 'deployment_stream'}</div>
                     <div className="text-[8px] font-mono opacity-20 mt-1">{new Date(s.last_active * 1000).toLocaleTimeString()}</div>
                   </button>
                 ))}
              </div>
           </div>
        </div>
        
        <div className="p-8 border-t border-white/5 bg-[#0d0d0f]">
           <button onClick={() => setIsAssetDrawerOpen(true)} className="w-full flex items-center gap-4 text-slate-400 hover:text-white transition-all">
              <div className="p-2.5 bg-blue-600/10 rounded-xl text-blue-500"><ArchiveIcon className="w-5 h-5" /></div>
              <span className="text-[12px] font-black uppercase tracking-widest">Project Assets</span>
              <ChevronRightIcon className="w-4 h-4 ml-auto opacity-30" />
           </button>
        </div>
      </aside>

      {/* ── Main Chat Interface ─────────────────────────────────────── */}
      <main className="flex-1 flex flex-col relative overflow-hidden bg-[#050505]">
        
        {/* Floating Top Nav */}
        <div className="absolute top-8 left-8 right-8 h-16 flex items-center justify-between z-[40]">
           <div className="flex items-center gap-4">
              <button 
                onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                className="w-12 h-12 flex items-center justify-center bg-white/5 hover:bg-white/10 rounded-2xl border border-white/5 text-slate-400 transition-all shadow-xl"
              >
                <LayoutGridIcon className="w-5 h-5" />
              </button>
              <div className="px-6 h-12 flex items-center gap-4 bg-[#0a0a0b]/80 backdrop-blur-xl rounded-2xl border border-white/5 shadow-2xl">
                 <div className="flex -space-x-3">
                    {Object.keys(roster).slice(0, 5).map((name, i) => (
                      <div key={i} className={`w-8 h-8 rounded-full bg-slate-800 border-2 border-[#0a0a0b] flex items-center justify-center text-[10px] font-black text-blue-500 ${roster[name].status === 'working' ? 'ring-2 ring-emerald-500 animate-pulse' : ''}`}>
                        {name[0]}
                      </div>
                    ))}
                    {Object.keys(roster).length > 5 && <div className="w-8 h-8 rounded-full bg-slate-900 border-2 border-[#0a0a0b] flex items-center justify-center text-[10px] font-black text-slate-500">+{Object.keys(roster).length - 5}</div>}
                 </div>
                 <div className="w-[1px] h-4 bg-white/10" />
                 <span className="text-[11px] font-black uppercase tracking-widest text-slate-500">{Object.keys(roster).length} Intelligence Nodes Ready</span>
              </div>
           </div>
           
           <div className="flex items-center gap-4">
              <div className="px-5 h-12 flex items-center justify-center bg-black/50 backdrop-blur-3xl rounded-2xl border border-white/5 shadow-2xl">
                 <div className="flex items-center gap-3">
                    <ActivityIcon className="w-4 h-4 text-blue-500" />
                    <span className="text-[10px] font-black uppercase tracking-[0.2em] text-white italic truncate max-w-[200px]">
                      {activeProjectId ? projects.find(p=>p.id===activeProjectId)?.name : 'Awaiting Mission'}
                    </span>
                 </div>
              </div>
              <button className="w-12 h-12 flex items-center justify-center bg-white/5 hover:bg-white/10 rounded-2xl border border-white/5 text-slate-400 transition-all font-black text-xs uppercase shadow-xl">
                 HUD
              </button>
           </div>
        </div>

        {/* The Swarm Visualizer Pulse (Background Overlay) */}
        <div className="absolute inset-0 z-0 pointer-events-none overflow-hidden opacity-30 select-none">
           <svg className="w-full h-full" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet">
              {/* Communication Lines */}
              {comms.map(c => {
                const start = agentPositions[c.from];
                const end = agentPositions[c.to];
                if (!start || !end) return null;
                return (
                  <g key={c.id}>
                    <line x1={start.x} y1={start.y} x2={end.x} y2={end.y} stroke="rgba(59, 130, 246, 0.4)" strokeWidth="0.5" strokeDasharray="1,1" className="animate-pulse" />
                    <circle r="0.8" fill="#3b82f6" className="animate-pulse">
                       <animateMotion path={`M ${start.x} ${start.y} L ${end.x} ${end.y}`} dur="0.8s" repeatCount="1" />
                    </circle>
                  </g>
                );
              })}
              
              {/* Agent Nodes */}
              {Object.keys(roster).map(name => {
                const pos = agentPositions[name];
                if (!pos) return null;
                return (
                  <g key={name} transform={`translate(${pos.x}, ${pos.y})`}>
                     <circle r="1.5" fill={roster[name].status === 'working' ? '#10b981' : '#1e293b'} className={`${roster[name].status === 'working' ? 'animate-pulse' : ''}`} />
                     <text y="-3" fontSize="1.5" textAnchor="middle" fill="rgba(255,255,255,0.2)" fontWeight="black" uppercase>{name}</text>
                  </g>
                );
              })}
           </svg>
        </div>

        {/* Chat Stream */}
        <div className="flex-1 overflow-y-auto custom-scrollbar relative z-10">
           <div className="max-w-4xl mx-auto px-10 pt-48 pb-64 space-y-16">
              {messages.length === 0 && (
                <div className="h-full flex flex-col items-center justify-center text-center space-y-8 animate-fade-in py-20 grayscale opacity-40">
                   <div className="w-24 h-24 rounded-[40px] bg-slate-900 flex items-center justify-center shadow-inner border border-white/5">
                      <MessageSquareIcon className="w-12 h-12 text-slate-700" />
                   </div>
                   <div className="space-y-4">
                      <h2 className="text-4xl font-black italic uppercase tracking-tighter text-white uppercase italic">Commander Console</h2>
                      <p className="text-sm font-bold text-slate-500 uppercase tracking-widest max-w-[300px] leading-loose">State-of-the-Art Multi-Agent Swarm Orchestration Interface</p>
                   </div>
                   <div className="flex gap-4">
                      {["Market Analysis", "Code Review", "Risk Summary"].map(tag => (
                        <button key={tag} onClick={() => setInput(prev => `${prev} ${tag}`.trim())} className="px-5 py-2.5 bg-white/5 hover:bg-blue-600/20 hover:text-blue-400 rounded-2xl border border-white/5 text-[10px] font-black uppercase tracking-widest transition-all">
                          {tag}
                        </button>
                      ))}
                   </div>
                </div>
              )}
              
              {messages.map((m, i) => (
                <div key={i} className={`flex gap-8 group animate-fade-in ${m.role === 'user' ? 'justify-end' : ''}`}>
                  {m.role !== 'user' && (
                    <div className="w-12 h-12 rounded-3xl bg-[#0a0a0b] border border-white/10 flex items-center justify-center shadow-2xl shrink-0 group-hover:scale-110 transition-transform">
                      {m.role === 'system' ? <ActivityIcon className="w-6 h-6 text-red-500" /> : <BotIcon className="w-7 h-7 text-blue-500" />}
                    </div>
                  )}
                  <div className={`relative max-w-[75%] px-10 py-8 rounded-[40px] text-[16px] leading-[1.8] shadow-2xl border transition-all ${
                    m.role === 'user' 
                      ? 'bg-blue-600 border-blue-500 text-white rounded-tr-none shadow-[0_20px_50px_rgba(37,99,235,0.4)]' 
                      : 'bg-[#0a0a0b]/80 backdrop-blur-md border-white/5 text-slate-200 rounded-tl-none ring-1 ring-white/5'
                  }`}>
                    {m.text.split('\n').map((line, j) => (
                      <p key={j} className="mb-4 last:mb-0 selection:bg-white/20">{line}</p>
                    ))}
                    
                    {/* Role Label */}
                    <div className={`absolute -bottom-6 ${m.role === 'user' ? 'right-4' : 'left-4'} text-[9px] font-black uppercase tracking-[0.3em] opacity-30 group-hover:opacity-100 transition-opacity`}>
                       {m.role} :: {new Date().toLocaleTimeString()}
                    </div>
                  </div>
                  {m.role === 'user' && (
                    <div className="w-12 h-12 rounded-3xl bg-blue-600 flex items-center justify-center shrink-0 text-white font-black text-xs uppercase shadow-2xl group-hover:scale-110 transition-transform italic">OP</div>
                  )}
                </div>
              ))}
              <div ref={messagesEndRef} />
           </div>
        </div>

        {/* Deep Command Bar */}
        <div className="absolute bottom-10 left-0 right-0 z-[50] px-10 pointer-events-none">
           <div className="max-w-4xl mx-auto flex items-end gap-6 p-4 bg-[#0a0a0b]/90 backdrop-blur-3xl rounded-[48px] border border-white/10 shadow-[0_40px_120px_rgba(0,0,0,0.9)] pointer-events-auto ring-1 ring-white/10 focus-within:ring-blue-500/30 transition-all">
              <div className="flex-1 flex flex-col px-8 py-3">
                 <div className="flex items-center gap-3 mb-2 opacity-30 focus-within:opacity-100 transition-opacity">
                    <CommandIcon className="w-4 h-4 text-blue-500" />
                    <span className="text-[10px] font-black text-slate-600 uppercase tracking-[0.2em]">{activeProjectId ? `Controlling Project` : 'No mission context selected'}</span>
                 </div>
                 <textarea 
                   className="w-full bg-transparent text-white py-2 focus:outline-none text-[18px] max-h-48 min-h-[54px] custom-scrollbar placeholder:text-slate-800 placeholder:italic font-black tracking-tight leading-relaxed"
                   placeholder={activeProjectId ? "Deploy swarm objective..." : "Select mission cluster..."}
                   value={input} onChange={e => setInput(e.target.value)}
                   disabled={!activeProjectId}
                   onKeyDown={e => { if(e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
                 />
              </div>
              <div className="flex gap-3 p-2">
                 <button onClick={() => sendMessage('steer')} className="w-16 h-16 flex items-center justify-center bg-white/5 hover:bg-emerald-600/20 text-emerald-500 rounded-[32px] transition-all border border-white/5 shadow-2xl">
                    <FastForwardIcon className="w-7 h-7" />
                 </button>
                 <button 
                  onClick={() => sendMessage('chat')} 
                  disabled={!activeProjectId}
                  className={`w-16 h-16 flex items-center justify-center rounded-[32px] transition-all border-none ${activeProjectId ? 'bg-blue-600 hover:bg-blue-500 text-white shadow-[0_20px_50px_rgba(37,99,235,0.4)] hover:scale-105 active:scale-95' : 'bg-slate-900 text-slate-700 opacity-30'}`}
                 >
                    <SendIcon className="w-7 h-7" />
                 </button>
              </div>
           </div>
        </div>
      </main>

      {/* ── Asset Drawer (Slide Out) ──────────────────────────────── */}
      <div className={`fixed inset-y-0 right-0 z-[100] bg-[#0d0d0f] border-l border-white/5 shadow-[-40px_0_100px_rgba(0,0,0,0.8)] transition-all duration-700 ease-[cubic-bezier(0.16, 1, 0.3, 1)] ${isAssetDrawerOpen ? 'w-[500px]' : 'w-0 overflow-hidden shadow-none'}`}>
         <div className="h-full flex flex-col w-[500px]">
             <div className="h-24 px-10 flex items-center justify-between border-b border-white/5">
                <div className="flex items-center gap-6">
                   <div className="p-3 bg-blue-600/20 rounded-2xl text-blue-500"><ArchiveIcon className="w-8 h-8" /></div>
                   <h2 className="text-2xl font-black italic tracking-tighter text-white uppercase italic">Project Assets</h2>
                </div>
                <button onClick={() => setIsAssetDrawerOpen(false)} className="w-12 h-12 flex items-center justify-center bg-white/5 hover:bg-red-500/20 hover:text-red-400 rounded-full transition-all">
                   <XIcon className="w-6 h-6" />
                </button>
             </div>
             
             <div className="flex-1 flex overflow-hidden">
                <div className="w-1/3 border-r border-white/5 p-6 overflow-y-auto custom-scrollbar">
                   <div className="flex items-center justify-between mb-8 px-2">
                      <span className="text-[10px] font-black text-slate-600 uppercase tracking-widest italic">Inventory</span>
                      <SearchIcon className="w-4 h-4 text-slate-700" />
                   </div>
                   <div className="space-y-1">
                      {fileTree.map(node => renderFileNode(node))}
                   </div>
                </div>
                <div className="flex-1 bg-black overflow-hidden flex flex-col relative">
                   {selectedFile ? (
                     <>
                        <div className="p-8 border-b border-white/5">
                           <div className="text-[11px] font-mono text-slate-400 font-bold mb-1 truncate">{selectedFile.split('/').pop()}</div>
                           <div className="text-[9px] text-slate-700 font-black uppercase tracking-widest font-mono truncate">{selectedFile}</div>
                        </div>
                        <div className="flex-1 overflow-auto p-10 font-mono text-[13px] text-slate-500 leading-relaxed custom-scrollbar selection:bg-blue-500/30">
                           {isLoadingFile ? 'DECODING...' : <pre><code>{fileContent}</code></pre>}
                        </div>
                     </>
                   ) : (
                     <div className="flex-1 flex flex-col items-center justify-center opacity-10">
                        <LockIcon className="w-24 h-24" />
                     </div>
                   )}
                </div>
             </div>
         </div>
      </div>

      {/* ── Global Flux Feed (Pinned Terminal) ────────────────────── */}
      <footer className="h-12 absolute bottom-0 left-0 right-0 bg-black/40 backdrop-blur-xl border-t border-white/5 flex items-center px-10 z-[60] pointer-events-none select-none opacity-40">
         <div className="flex-1 flex items-center gap-12 overflow-hidden">
            <div className="flex items-center gap-2">
               <TermIcon className="w-4 h-4 text-blue-500" />
               <span className="text-[10px] font-black text-slate-600 uppercase tracking-widest">Global Telemetry Flux</span>
            </div>
            <div className="flex-1 flex gap-8 whitespace-nowrap overflow-hidden items-center group">
               {telemetry.slice(0, 5).map(log => (
                 <div key={log.id} className="text-[9px] font-mono flex items-center gap-2">
                    <span className="text-blue-500 font-bold">[{log.agent}]</span> 
                    <span className="text-slate-500 italic">{log.tool} :: {log.result?.slice(0, 30)}</span>
                    <span className="text-slate-800">::</span>
                 </div>
               ))}
            </div>
         </div>
         <div className="text-[9px] font-black text-slate-800 tracking-[0.4em] uppercase">Core Rev 42.1</div>
      </footer>

      {/* ── Simple Inspection Modal (Clean) ───────────────────────── */}
      {inspectAgent && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-24 bg-black/95 backdrop-blur-3xl animate-fade-in">
           <div className="w-full max-w-4xl h-full bg-[#0a0a0b] border border-white/10 rounded-[64px] shadow-[0_0_120px_rgba(0,0,0,1)] overflow-hidden flex flex-col border-b-[8px] border-b-blue-600">
              <div className="h-24 px-12 flex items-center justify-between border-b border-white/5 bg-black">
                 <div className="flex items-center gap-8">
                    <div className="w-14 h-14 bg-blue-600 rounded-3xl flex items-center justify-center shadow-xl shadow-blue-900/40"><BotIcon className="w-8 h-8 text-white" /></div>
                    <div className="text-2xl font-black italic tracking-tighter text-white uppercase italic">INSPECT: {inspectAgent}</div>
                 </div>
                 <button onClick={() => setInspectAgent(null)} className="w-14 h-14 flex items-center justify-center bg-white/5 hover:bg-white/10 rounded-full transition-all">
                    <XIcon className="w-7 h-7" />
                 </button>
              </div>
              <div className="flex-1 overflow-y-auto p-16 custom-scrollbar space-y-12">
                 {(traces[inspectAgent] || []).map((t, idx) => (
                   <div key={idx} className="flex gap-10 items-start">
                      <div className="w-3 h-3 rounded-full mt-2 shrink-0 bg-blue-600 shadow-[0_0_15px_blue]" />
                      <div className="flex-1">
                         <div className="flex items-center gap-4 mb-4 opacity-50">
                            <span className="text-[11px] font-black text-slate-400 tracking-widest">{t.ts}</span>
                            <span className="text-[10px] font-bold uppercase tracking-widest">{t.type}</span>
                         </div>
                         <div className="p-10 bg-black/40 rounded-[50px] border border-white/5 text-[16px] text-slate-400 leading-relaxed font-sans whitespace-pre-wrap">
                            {t.content}
                         </div>
                      </div>
                   </div>
                 ))}
              </div>
           </div>
        </div>
      )}

      <style dangerouslySetInnerHTML={{ __html: `
        .custom-scrollbar::-webkit-scrollbar { width: 4px; height: 4px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(59, 130, 246, 0.2); border-radius: 10px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(59, 130, 246, 0.4); }
        @keyframes fade-in { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        .animate-fade-in { animation: fade-in 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
      `}} />

    </div>
  );
}
