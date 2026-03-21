// CMAS Web Chat Client Integration
(function() {
    const messagesEl = document.getElementById('messages');
    const inputEl = document.getElementById('input');
    const formEl = document.getElementById('input-form');
    const statusEl = document.getElementById('status');
    const typingEl = document.getElementById('typing');
    const sendBtn = document.getElementById('send-btn');
    const steerBtn = document.getElementById('steer-btn');
    const sessionListEl = document.getElementById('session-list');
    const currentSessionLabel = document.getElementById('current-session-label');
    const rosterEl = document.getElementById('agent-roster');
    const telemetryEl = document.getElementById('telemetry-log');

    let ws = null;
    let sessionId = localStorage.getItem('cmas_session_id') || '';
    let reconnectDelay = 1000;

    function connect() {
        if (ws) {
            ws.onclose = null;
            ws.close();
        }

        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        let url = `${proto}//${location.host}/ws`;
        if (sessionId) url += `?session_id=${sessionId}`;

        ws = new WebSocket(url);

        ws.onopen = function() {
            statusEl.textContent = 'connected';
            statusEl.className = 'status connected';
            reconnectDelay = 1000;
            sendBtn.disabled = false;
            
            // Request active sessions list on connect
            ws.send(JSON.stringify({ type: 'get_sessions' }));
        };

        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);

            switch (data.type) {
                case 'session':
                    // Triggered by connection, or by backend LLM tool 'switch_session'
                    if (sessionId !== data.session_id) {
                        messagesEl.innerHTML = '';
                        addMessage('system', 'Switched to session: ' + data.session_id);
                    }
                    sessionId = data.session_id;
                    localStorage.setItem('cmas_session_id', sessionId);
                    currentSessionLabel.textContent = `Session: ${sessionId}`;
                    // Refresh session list
                    ws.send(JSON.stringify({ type: 'get_sessions' }));
                    break;

                case 'session_list':
                    renderSessions(data.sessions);
                    break;

                case 'roster_init':
                    renderRoster(data.agents);
                    break;
                    
                case 'agent_status':
                    updateAgentStatus(data.agent, data.status, data.task);
                    break;
                    
                case 'telemetry':
                    logTelemetry(data);
                    break;

                case 'message':
                    addMessage('assistant', data.text);
                    break;

                case 'proactive':
                    addMessage('proactive', data.text);
                    break;

                case 'error':
                    addMessage('error', data.text);
                    break;

                case 'typing':
                    typingEl.classList.toggle('hidden', !data.status);
                    break;
            }
        };

        ws.onclose = function() {
            statusEl.textContent = 'disconnected';
            statusEl.className = 'status disconnected';
            sendBtn.disabled = true;
            typingEl.classList.add('hidden');
            setTimeout(connect, reconnectDelay);
            reconnectDelay = Math.min(reconnectDelay * 2, 30000);
        };

        ws.onerror = function() {
            ws.close();
        };
    }

    function renderSessions(sessions) {
        sessionListEl.innerHTML = '';
        if (!sessions || sessions.length === 0) {
            sessionListEl.innerHTML = '<div class="loading">No recent sessions.</div>';
            return;
        }

        sessions.forEach(s => {
            const div = document.createElement('div');
            div.className = 'session-item' + (s.id === sessionId ? ' active' : '');
            
            const title = document.createElement('div');
            title.textContent = s.summary || s.id.substring(0,8);
            title.style.fontWeight = 'bold';
            
            const time = document.createElement('div');
            time.className = 'session-time';
            const date = new Date(s.last_active * 1000);
            time.textContent = date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
            
            div.appendChild(title);
            div.appendChild(time);
            
            div.onclick = () => {
                sessionId = s.id;
                localStorage.setItem('cmas_session_id', sessionId);
                connect(); // Reconnect to bind to the new session
            };
            sessionListEl.appendChild(div);
        });
    }
    
    // --- Observability HUD Functions ---
    let agentStatuses = {};
    
    function renderRoster(agents) {
        agentStatuses = {};
        rosterEl.innerHTML = '';
        if (!agents || agents.length === 0) {
            rosterEl.innerHTML = '<div class="label-muted">No specialized agents loaded.</div>';
            return;
        }
        agents.forEach(a => updateAgentStatus(a.name, a.status, a.current_task));
    }
    
    function updateAgentStatus(name, status, task) {
        agentStatuses[name] = {status, task};
        rosterEl.innerHTML = '';
        Object.keys(agentStatuses).forEach(k => {
            const a = agentStatuses[k];
            const div = document.createElement('div');
            div.className = `agent-card ${a.status}`;
            div.innerHTML = `<div class="agent-name">${k} [${a.status}]</div>
                             <div class="agent-task">${a.task || ''}</div>`;
            rosterEl.appendChild(div);
        });
    }
    
    function logTelemetry(data) {
        const div = document.createElement('div');
        div.className = 'telemetry-entry' + (data.allowed ? '' : ' denied');
        
        const now = new Date();
        const ts = `${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}:${now.getSeconds().toString().padStart(2,'0')}`;
        
        div.innerHTML = `<span class="ts">[${ts}]</span> 
                         <span class="agent">${data.agent}</span> 
                         used <span class="tool">${data.tool}</span><br>
                         ${data.args ? `<span style="color:#6b7280; font-size:10px;">${data.args}</span>` : ''}`;
                         
        telemetryEl.appendChild(div);
        telemetryEl.scrollTop = telemetryEl.scrollHeight;
        
        // Keep log size managed
        if (telemetryEl.children.length > 50) {
            telemetryEl.removeChild(telemetryEl.firstChild);
        }
    }

    // --- Core Chat Functions ---
    function addMessage(role, text) {
        const div = document.createElement('div');
        div.className = `message ${role}`;
        
        // Simple markdown parsing for bold and links
        let formatted = text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank" style="color:var(--accent-color)">$1</a>')
            .replace(/\n/g, '<br>');
            
        div.innerHTML = formatted;
        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function sendMessage() {
        const text = inputEl.value.trim();
        if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;

        addMessage('user', text);
        ws.send(JSON.stringify({ type: 'chat', text: text }));
        inputEl.value = '';
        inputEl.style.height = 'auto';
    }

    // ── UI Event Listeners ──

    formEl.addEventListener('submit', function(e) {
        e.preventDefault();
        sendMessage();
    });

    inputEl.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    inputEl.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 150) + 'px';
    });
    
    // New Session
    document.getElementById('new-session-btn').addEventListener('click', () => {
        sessionId = ''; 
        localStorage.removeItem('cmas_session_id');
        messagesEl.innerHTML = '';
        connect(); 
    });

    // Set Project Focus
    document.getElementById('project-btn').addEventListener('click', () => {
        const proj = document.getElementById('project-input').value.trim();
        if (!proj) return;
        ws.send(JSON.stringify({ type: 'set_project', project: proj }));
        document.getElementById('project-input').value = '';
    });

    // Add Reminder
    document.getElementById('rem-btn').addEventListener('click', () => {
        const desc = document.getElementById('rem-desc').value.trim();
        const when = document.getElementById('rem-when').value.trim();
        if (!desc || !when) return;
        
        document.getElementById('rem-btn').textContent = '...';
        ws.send(JSON.stringify({ type: 'add_reminder', description: desc, when: when }));
        
        setTimeout(() => {
            document.getElementById('rem-desc').value = '';
            document.getElementById('rem-when').value = '';
            document.getElementById('rem-btn').textContent = 'Add Reminder';
        }, 1000);
    });
    
    // Interactive Steer
    steerBtn.addEventListener('click', () => {
        const text = inputEl.value.trim();
        if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
        
        ws.send(JSON.stringify({ type: 'steer', text: text }));
        addMessage('user', `<i>[Steering Override]: ${text}</i>`);
        inputEl.value = '';
        inputEl.style.height = 'auto';
    });

    // Start connection
    connect();
})();
