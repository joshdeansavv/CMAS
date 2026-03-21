import React, { useState, useEffect, useRef } from 'react';
import { Send, Clock, Plus, Zap, User, Bot, Activity, Hash, AlertTriangle, FastForward } from 'lucide-react';

export default function App() {
  const [ws, setWs] = useState(null);
  const [sessionId, setSessionId] = useState(localStorage.getItem('cmas_session_id') || '');
  const [sessions, setSessions] = useState([]);
  const [messages, setMessages] = useState([]);
  const [roster, setRoster] = useState({});
  const [telemetry, setTelemetry] = useState([]);
  const [input, setInput] = useState('');
  const [remDesc, setRemDesc] = useState('');
  const [remWhen, setRemWhen] = useState('');
  const [project, setProject] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [connected, setConnected] = useState(false);

  const messagesEndRef = useRef(null);
  const telemetryEndRef = useRef(null);

  // Auto-scroll hooks
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);
  
  useEffect(() => {
    telemetryEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [telemetry]);

  // WebSocket Connection
  useEffect(() => {
    let socket = null;
    let reconnectTimeout = null;
    let isSubscribed = true;

    const connect = () => {
      const url = `ws://${window.location.host}/ws?session_id=${sessionId}&user_id=web_user`;
      socket = new WebSocket(url);

      socket.onopen = () => {
        if (!isSubscribed) return;
        setConnected(true);
        socket.send(JSON.stringify({ type: 'get_sessions' }));
        socket.send(JSON.stringify({ type: 'get_history' }));
      };

      socket.onclose = () => {
        if (!isSubscribed) return;
        setConnected(false);
        reconnectTimeout = setTimeout(connect, 3000); // Reconnect
      };

      socket.onmessage = (e) => {
        if (!isSubscribed) return;
        const data = JSON.parse(e.data);
        handleMessage(data);
      };

      setWs(socket);
    };

    connect();

    return () => {
      isSubscribed = false;
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (socket) socket.close();
    };
  }, [sessionId]);

  const handleMessage = (data) => {
    switch (data.type) {
      case 'session':
        localStorage.setItem('cmas_session_id', data.session_id);
        break;
      case 'session_list':
        setSessions(data.sessions || []);
        break;
      case 'history':
        setMessages((data.messages || []).map(m => ({
          role: m.role, text: m.content
        })));
        break;
      case 'roster_init':
        const newRoster = {};
        (data.agents || []).forEach(a => { newRoster[a.name] = a; });
        setRoster(newRoster);
        break;
      case 'agent_status':
        setRoster(prev => ({
          ...prev,
          [data.agent]: { name: data.agent, status: data.status, current_task: data.task }
        }));
        break;
      case 'telemetry':
        setTelemetry(prev => {
          const now = new Date();
          const ts = `${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}:${now.getSeconds().toString().padStart(2,'0')}`;
          const newEntry = { ...data, ts, id: Date.now() + Math.random() };
          const log = [...prev, newEntry];
          return log.length > 50 ? log.slice(1) : log;
        });
        break;
      case 'message':
      case 'proactive':
      case 'error':
        setMessages(prev => [...prev, { 
          role: data.type === 'error' ? 'system' : 'assistant', 
          text: data.text 
        }]);
        break;
      case 'typing':
        setIsTyping(data.status);
        break;
    }
  };

  const sendMessage = (type = 'chat', customText = null) => {
    const textToSend = customText !== null ? customText : input.trim();
    if (!textToSend || !ws || ws.readyState !== WebSocket.OPEN) return;

    if (type !== 'steer') {
      setMessages(prev => [...prev, { role: 'user', text: textToSend }]);
    } else {
      setMessages(prev => [...prev, { role: 'user', text: `*[Steering Override]: ${textToSend}*` }]);
    }
    
    ws.send(JSON.stringify({ type, text: textToSend }));
    if (customText === null) setInput('');
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const newSession = () => {
    localStorage.removeItem('cmas_session_id');
    setSessionId('');
    setMessages([]);
    setTelemetry([]);
  };

  const switchSession = (id) => {
    setSessionId(id);
    localStorage.setItem('cmas_session_id', id);
    setMessages([]);
    setTelemetry([]);
    // Let React's useEffect cleanup handle the actual socket teardown to prevent ghost connections
  };

  return (
    <div className="flex h-screen bg-slate-900 text-slate-100 overflow-hidden font-sans">
      
      {/* Left Sidebar - Sessions & Settings */}
      <aside className="w-72 glass-panel flex flex-col border-r border-slate-700/50 shadow-2xl relative z-10">
        <div className="p-5 border-b border-slate-700/50">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-500/20 flex items-center justify-center">
              <Zap className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-emerald-400 bg-clip-text text-transparent">CMAS Core</h1>
              <div className="text-xs text-slate-400">{connected ? 'Connected' : 'Connecting...'}</div>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Sessions</h2>
            <button onClick={newSession} className="text-blue-400 hover:text-blue-300">
              <Plus className="w-4 h-4" />
            </button>
          </div>
          <div className="space-y-2">
            {sessions.map(s => (
              <button 
                key={s.id} 
                onClick={() => switchSession(s.id)}
                className={`w-full text-left p-3 rounded-lg text-sm transition-all duration-200 ${
                  s.id === sessionId ? 'bg-blue-500/20 text-blue-200 border border-blue-500/30' : 'hover:bg-slate-800/60 text-slate-300'
                }`}
              >
                <div className="truncate font-medium">{s.summary}</div>
                <div className="text-xs text-slate-500 mt-1">
                  {new Date(s.last_active * 1000).toLocaleDateString()}
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="p-4 border-t border-slate-700/50 bg-slate-800/30">
          <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Custom Reminder</h2>
          <div className="space-y-2">
            <input 
              className="w-full text-sm bg-slate-900/50 border border-slate-700 rounded-md p-2 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none" 
              placeholder="Remind me to..." 
              value={remDesc} 
              onChange={e => setRemDesc(e.target.value)} 
            />
            <input 
              className="w-full text-sm bg-slate-900/50 border border-slate-700 rounded-md p-2 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none" 
              placeholder="When (e.g. in 5 mins)" 
              value={remWhen} 
              onChange={e => setRemWhen(e.target.value)} 
            />
            <button 
              onClick={() => {
                ws?.send(JSON.stringify({ type: 'add_reminder', description: remDesc, when: remWhen }));
                setRemDesc(''); setRemWhen('');
              }}
              className="w-full bg-slate-700 hover:bg-slate-600 text-slate-200 text-sm py-2 rounded-md font-medium transition-colors flex items-center justify-center gap-2"
            >
              <Clock className="w-4 h-4" /> Add
            </button>
          </div>
        </div>
      </aside>

      {/* Main Chat Area */}
      <main className="flex-1 flex flex-col relative z-0">
        <header className="h-16 border-b border-slate-800/50 flex items-center px-6 justify-between bg-slate-900/50 backdrop-blur-md relative z-10">
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full animate-pulse bg-emerald-500" />
            <span className="text-sm font-medium text-slate-300">Active Bridge</span>
          </div>
          <div className="flex items-center gap-3">
            <Hash className="w-4 h-4 text-slate-500" />
            <input 
              className="bg-transparent border-b border-slate-700 text-sm text-slate-200 px-2 py-1 w-48 focus:border-blue-500 outline-none placeholder:text-slate-600"
              placeholder="Global Project Focus..."
              value={project}
              onChange={e => setProject(e.target.value)}
            />
            <button 
              onClick={() => ws?.send(JSON.stringify({ type: 'set_project', project }))}
              className="text-xs px-3 py-1 bg-blue-500/10 text-blue-400 rounded-full hover:bg-blue-500/20 transition-colors"
            >
              Focus
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {messages.map((m, i) => (
            <div key={i} className={`flex gap-4 animate-slide-in ${m.role === 'user' ? 'justify-end' : ''}`}>
              {m.role !== 'user' && (
                <div className="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center shrink-0 border border-slate-700">
                  <Bot className="w-5 h-5 text-emerald-400" />
                </div>
              )}
              <div className={`max-w-[80%] rounded-2xl px-5 py-3 text-[15px] leading-relaxed shadow-sm ${
                m.role === 'user' 
                  ? 'bg-blue-600 text-white rounded-br-none' 
                  : m.role === 'system'
                  ? 'bg-red-500/10 text-red-200 border border-red-500/20 rounded-bl-none'
                  : 'bg-slate-800 text-slate-200 rounded-bl-none shadow-md border border-slate-700/50'
              }`}>
                {m.text.split('\\n').map((line, j) => (
                  <p key={j} className="mb-2 last:mb-0 min-h-[1em]">
                    {line.replace(/([*_~`])/g, '') /* Basic markdown strip for simplicity */}
                  </p>
                ))}
              </div>
              {m.role === 'user' && (
                <div className="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center shrink-0 shadow-md">
                  <User className="w-5 h-5 text-white" />
                </div>
              )}
            </div>
          ))}
          {isTyping && (
            <div className="flex gap-4 animate-slide-in">
              <div className="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center shrink-0 border border-slate-700">
                <Bot className="w-5 h-5 text-emerald-400" />
              </div>
              <div className="bg-slate-800 px-5 py-4 rounded-2xl rounded-bl-none border border-slate-700/50 w-24 flex items-center justify-center gap-1 shadow-md">
                <div className="typing-dot" />
                <div className="typing-dot" />
                <div className="typing-dot" />
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="p-4 bg-slate-900/80 backdrop-blur-lg border-t border-slate-800">
          <div className="flex gap-2 max-w-4xl mx-auto items-end">
            <textarea
              className="flex-1 max-h-48 min-h-[52px] bg-slate-800/80 text-slate-100 border border-slate-700/50 rounded-xl px-4 py-3 resize-none focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all shadow-inner"
              placeholder="Ask CMAS, assign tasks, or use specialized tools..."
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyPress}
            />
            <div className="flex flex-col gap-2 shrink-0">
              <button 
                onClick={() => sendMessage('chat')}
                className="bg-blue-600 hover:bg-blue-500 text-white rounded-xl p-3 px-4 shadow-lg shadow-blue-500/20 transition-all flex items-center justify-center"
              >
                <Send className="w-5 h-5" />
              </button>
              <button 
                onClick={() => sendMessage('steer')}
                title="Interrupt Agent / Force Course Correction"
                className="bg-emerald-600/20 hover:bg-emerald-600/40 text-emerald-400 border border-emerald-500/30 rounded-xl p-2 px-3 shadow-lg transition-all flex items-center justify-center group"
              >
                <FastForward className="w-5 h-5 group-hover:scale-110 transition-transform" />
              </button>
            </div>
          </div>
        </div>
      </main>

      {/* Right Sidebar - Roster & Telemetry HUD */}
      <aside className="w-80 glass-panel flex flex-col border-l border-slate-700/50 shadow-2xl relative z-10">
        <div className="p-4 border-b border-slate-700/50 bg-slate-800/20">
          <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
            <Activity className="w-4 h-4" /> Agent Roster
          </h2>
        </div>
        
        <div className="p-4 max-h-[40%] overflow-y-auto custom-scrollbar border-b border-slate-700/50">
          {Object.keys(roster).length === 0 ? (
            <div className="text-sm text-slate-500 italic flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" /> No specialized agents running
            </div>
          ) : (
            <div className="space-y-3">
              {Object.values(roster).map((a, i) => (
                <div key={i} className={`p-3 rounded-lg border flex flex-col gap-1 shadow-sm transition-all
                  ${a.status === 'working' || a.status === 'in_progress' ? 'bg-emerald-500/10 border-emerald-500/30' 
                    : a.status === 'error' ? 'bg-red-500/10 border-red-500/30' 
                    : 'bg-slate-800/50 border-slate-700'}
                `}>
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-sm text-slate-200">{a.name}</span>
                    <span className={`text-[10px] uppercase font-bold px-2 rounded-full 
                      ${a.status === 'working' ? 'bg-emerald-500/20 text-emerald-400' 
                        : a.status === 'error' ? 'bg-red-500/20 text-red-400' 
                        : 'bg-slate-700 text-slate-400'}`}>{a.status}</span>
                  </div>
                  {a.current_task && (
                    <div className="text-xs text-slate-400 truncate mt-1">
                      <ChevronRight className="w-3 h-3 inline-block mr-1 opacity-50"/>
                      {a.current_task}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="p-4 bg-slate-800/40">
          <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
            <Zap className="w-4 h-4" /> Live Telemetry
          </h2>
        </div>
        
        <div className="flex-1 p-4 bg-black/40 overflow-y-auto custom-scrollbar font-mono text-xs">
          {telemetry.length === 0 ? (
            <div className="text-slate-600 italic">Awaiting events...</div>
          ) : (
            <div className="space-y-3">
              {telemetry.map(log => (
                <div key={log.id} className={`pb-3 border-b border-slate-800 last:border-0 ${!log.allowed && 'text-red-400'}`}>
                  <div className="flex gap-2 text-slate-500 mb-1">
                    <span>[{log.ts}]</span>
                    <span className="text-blue-400 font-semibold">{log.agent}</span>
                  </div>
                  <div className="text-slate-300">
                    <span className="text-emerald-400">ƒ</span> {log.tool}(
                      <span className="text-slate-500">{log.args}</span>
                    )
                  </div>
                </div>
              ))}
              <div ref={telemetryEndRef} />
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
