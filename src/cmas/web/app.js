// CMAS Web Chat Client
(function() {
    const messagesEl = document.getElementById('messages');
    const inputEl = document.getElementById('input');
    const formEl = document.getElementById('input-form');
    const statusEl = document.getElementById('status');
    const typingEl = document.getElementById('typing');
    const sendBtn = document.getElementById('send-btn');

    let ws = null;
    let sessionId = localStorage.getItem('cmas_session_id') || '';
    let reconnectDelay = 1000;

    function connect() {
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        let url = `${proto}//${location.host}/ws`;
        if (sessionId) url += `?session_id=${sessionId}`;

        ws = new WebSocket(url);

        ws.onopen = function() {
            statusEl.textContent = 'connected';
            statusEl.className = 'status connected';
            reconnectDelay = 1000;
            sendBtn.disabled = false;
        };

        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);

            switch (data.type) {
                case 'session':
                    sessionId = data.session_id;
                    localStorage.setItem('cmas_session_id', sessionId);
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
            // Auto-reconnect with backoff
            setTimeout(connect, reconnectDelay);
            reconnectDelay = Math.min(reconnectDelay * 2, 30000);
        };

        ws.onerror = function() {
            ws.close();
        };
    }

    function addMessage(role, text) {
        const div = document.createElement('div');
        div.className = `message ${role}`;
        div.textContent = text;
        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function sendMessage() {
        const text = inputEl.value.trim();
        if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;

        addMessage('user', text);
        ws.send(JSON.stringify({ text: text }));
        inputEl.value = '';
        inputEl.style.height = 'auto';
    }

    formEl.addEventListener('submit', function(e) {
        e.preventDefault();
        sendMessage();
    });

    // Enter to send, Shift+Enter for newline
    inputEl.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-resize textarea
    inputEl.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 150) + 'px';
    });

    // Start connection
    connect();
})();
