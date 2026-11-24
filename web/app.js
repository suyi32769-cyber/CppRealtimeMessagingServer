'use strict';

const $ = id => document.getElementById(id);
const state = {socket: null, user: null, instance: null, rooms: new Map(), current: null, historyPending: new Set()};
const encoder = new TextEncoder();
const time = value => {
  const date = value ? new Date(value) : new Date();
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit', second: '2-digit'});
};
const roomName = () => $('room-id').value.trim();
const connected = () => state.socket?.readyState === WebSocket.OPEN && Boolean(state.user);
const active = () => connected() && state.current && state.rooms.has(state.current);

function eventLog(text, error = false) {
  const list = $('events');
  list.querySelector('.event-empty')?.remove();
  const item = document.createElement('div'); item.className = `event${error ? ' error' : ''}`;
  const dot = document.createElement('i'), body = document.createElement('div'), label = document.createElement('span'), stamp = document.createElement('small');
  label.textContent = text; stamp.textContent = time(); body.append(label, stamp); item.append(dot, body); list.prepend(item);
  while (list.children.length > 80) list.lastElementChild.remove();
}
function updateUI() {
  const isConnected = connected(), hasRoom = Boolean(active()), busy = state.socket && !isConnected && state.socket.readyState !== WebSocket.CLOSED;
  $('connect').disabled = Boolean(busy);
  $('connect').firstElementChild.textContent = isConnected ? '断开连接' : busy ? '正在连接…' : '连接服务';
  $('identity').disabled = isConnected || busy; $('instance').disabled = isConnected || busy;
  $('create').disabled = !isConnected; $('join').disabled = !isConnected;
  for (const id of ['history', 'leave', 'send', 'content', 'load-more']) $(id).disabled = !hasRoom || (['history', 'load-more'].includes(id) && state.historyPending.has(state.current));
  $('connection-dot').classList.toggle('online', isConnected); $('overview-dot').classList.toggle('online', isConnected);
  $('connection-label').textContent = isConnected ? '连接正常' : busy ? '连接中' : '尚未连接';
  $('overview-status').textContent = isConnected ? '已连接' : busy ? '连接中' : '未连接';
  $('overview-user').textContent = state.user || '—'; $('overview-instance').textContent = state.instance ? `实例 ${state.instance}` : '—';
  $('top-user').textContent = state.user ? `${state.user} / 实例 ${state.instance}` : '未连接';
  $('overview-rooms').textContent = String(state.rooms.size); $('room-count').textContent = String(state.rooms.size);
  $('current-room').textContent = state.current || '尚未选择房间';
  const list = $('room-list'); list.replaceChildren();
  if (!state.rooms.size) {const empty = document.createElement('div'); empty.className = 'room-empty'; empty.textContent = '加入后，房间会显示在这里'; list.append(empty);}
  for (const room of state.rooms.keys()) {
    const button = document.createElement('button'); button.className = `room-item${room === state.current ? ' selected' : ''}`;
    const mark = document.createElement('span'); mark.textContent = '#'; button.append(mark, document.createTextNode(room));
    button.addEventListener('click', () => {state.current = room; updateUI(); renderMessages();}); list.append(button);
  }
  $('load-more-wrap').hidden = !hasRoom || !state.rooms.get(state.current).hasMore;
}
function sendFrame(value) {
  if (!connected()) { eventLog('请先连接服务', true); return false; }
  state.socket.send(JSON.stringify(value)); return true;
}
function checkRoom() {
  const room = roomName();
  if (!room || encoder.encode(room).length > 64) { eventLog('房间 ID 不能为空，且不能超过 64 字节', true); return null; }
  return room;
}
function appendMessage(message) {
  const room = state.rooms.get(message.room_id);
  if (!room || !Number.isSafeInteger(message.message_id) || message.message_id <= 0) return;
  if (!room.messages.has(message.message_id)) room.messages.set(message.message_id, message);
}
function renderMessages() {
  const list = $('messages'); list.replaceChildren();
  const room = state.rooms.get(state.current);
  if (!room || !room.messages.size) {
    const empty = document.createElement('div'); empty.className = 'empty-state';
    const art = document.createElement('div'); art.className = 'empty-art';
    const one = document.createElement('span'), two = document.createElement('span'); one.className = 'bubble-one'; one.textContent = '···'; two.className = 'bubble-two'; two.textContent = '✳'; art.append(one, two);
    const title = document.createElement('h3'); title.textContent = room ? '还没有消息' : '对话从这里开始';
    const note = document.createElement('p'); note.textContent = room ? '发送第一条消息，或加载历史消息。' : '连接服务并加入房间后，消息会实时显示在这里。';
    empty.append(art, title, note); list.append(empty); return;
  }
  const messages = [...room.messages.values()].sort((a, b) => a.message_id - b.message_id);
  for (const message of messages) {
    const mine = message.sender_id === state.user, row = document.createElement('div'); row.className = `message-row${mine ? ' mine' : ''}`;
    const avatar = document.createElement('div'); avatar.className = 'avatar'; avatar.textContent = (message.sender_id || '?').slice(0, 1).toUpperCase();
    const content = document.createElement('div'); content.className = 'message-content';
    const meta = document.createElement('div'); meta.className = 'message-meta';
    const name = document.createElement('b'); name.textContent = mine ? '你' : message.sender_id; meta.append(name, document.createTextNode(time(message.created_at)));
    const bubble = document.createElement('div'); bubble.className = 'message-bubble'; bubble.textContent = message.content;
    const bottom = document.createElement('div'); bottom.className = 'message-bottom';
    const id = document.createElement('span'); id.textContent = `#${message.message_id}`; bottom.append(id);
    if (room.acked.has(message.message_id)) {const ack = document.createElement('span'); ack.textContent = '已确认'; bottom.append(ack);}
    else {const ack = document.createElement('button'); ack.className = 'ack-button'; ack.textContent = '确认收到'; ack.addEventListener('click', () => {if (sendFrame({type:'ack', room_id:message.room_id, message_id:message.message_id})) eventLog(`请求确认消息 #${message.message_id}`);}); bottom.append(ack);}
    content.append(meta, bubble, bottom); row.append(avatar, content); list.append(row);
  }
  list.scrollTop = list.scrollHeight;
}
function history(after) {
  if (!active() || state.historyPending.has(state.current)) return;
  state.historyPending.add(state.current);
  if (!sendFrame({type:'history', room_id:state.current, after_message_id:after})) state.historyPending.delete(state.current);
  else eventLog(`请求历史消息 · ${state.current}`);
  updateUI();
}
function onResponse(data) {
  switch (data.type) {
    case 'auth_ok':
      state.user = data.user_id; eventLog(`身份验证成功 · ${data.user_id}`); updateUI(); break;
    case 'room_created':
      eventLog(`房间创建成功 · ${data.room_id}`); sendFrame({type:'join', room_id:data.room_id}); break;
    case 'joined':
      if (!state.rooms.has(data.room_id)) state.rooms.set(data.room_id, {messages:new Map(), acked:new Set(), historyCursor:0, hasMore:false});
      state.current = data.room_id; eventLog(`已加入房间 · ${data.room_id}`); updateUI(); renderMessages(); history(0); break;
    case 'left':
      state.rooms.delete(data.room_id); state.historyPending.delete(data.room_id); if (state.current === data.room_id) state.current = state.rooms.keys().next().value || null;
      eventLog(`已退出房间 · ${data.room_id}`); updateUI(); renderMessages(); break;
    case 'message':
      appendMessage(data); eventLog(`收到消息 #${data.message_id} · ${data.room_id}`); if (state.current === data.room_id) renderMessages(); break;
    case 'send_ok':
      eventLog(`消息已保存 #${data.message_id}${data.duplicate ? ' · 重复请求' : ''}`); break;
    case 'history': {
      const room = state.rooms.get(data.room_id);
      if (room && Array.isArray(data.messages)) {
        for (const message of data.messages) appendMessage(message);
        room.historyCursor = data.messages.length ? data.messages[data.messages.length - 1].message_id : data.after_message_id;
        room.hasMore = data.messages.length === 100;
        eventLog(`加载 ${data.messages.length} 条历史消息 · ${data.room_id}`);
      }
      state.historyPending.delete(data.room_id); updateUI(); if (state.current === data.room_id) renderMessages(); break;
    }
    case 'ack_ok':
      state.rooms.get(data.room_id)?.acked.add(data.message_id); eventLog(`已确认消息 #${data.message_id}`); if (state.current === data.room_id) renderMessages(); break;
    case 'error':
      state.historyPending.clear(); eventLog(`服务返回错误：${data.message || '未知错误'}`, true); updateUI(); break;
    case 'pong': break;
    default: eventLog(`收到服务事件：${String(data.type || '未知')}`);
  }
}
$('connect').addEventListener('click', () => {
  if (state.socket) {state.socket.close(); return;}
  const chosen = $('instance').value, port = chosen === 'A' ? 19001 : 19002, selectedUser = $('identity').value;
  state.instance = chosen;
  const socket = new WebSocket(`ws://127.0.0.1:${port}`); state.socket = socket; updateUI();
  socket.addEventListener('open', () => {eventLog(`已连接实例 ${chosen}，正在认证`); socket.send(JSON.stringify({type:'auth', token:`demo-${selectedUser}`}));});
  socket.addEventListener('message', event => {try {onResponse(JSON.parse(event.data));} catch {eventLog('无法解析服务器响应', true);}});
  socket.addEventListener('error', () => eventLog('连接失败，请确认本地启动器和服务器正在运行', true));
  socket.addEventListener('close', () => {if (state.socket !== socket) return; state.socket = null; state.user = null; state.instance = null; state.rooms.clear(); state.current = null; state.historyPending.clear(); eventLog('连接已断开'); updateUI(); renderMessages();});
});
$('create').addEventListener('click', () => {const room = checkRoom(); if (room) sendFrame({type:'create_room', room_id:room});});
$('join').addEventListener('click', () => {const room = checkRoom(); if (room) sendFrame({type:'join', room_id:room});});
$('leave').addEventListener('click', () => {if (active()) sendFrame({type:'leave', room_id:state.current});});
$('history').addEventListener('click', () => history(0));
$('load-more').addEventListener('click', () => {if (active()) history(state.rooms.get(state.current).historyCursor);});
$('send').addEventListener('click', () => {
  const content = $('content').value;
  if (!content.trim() || encoder.encode(content).length > 4096) {eventLog('消息不能为空，且不能超过 4096 字节', true); return;}
  const id = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  if (sendFrame({type:'send', room_id:state.current, client_msg_id:id, content})) {$('content').value = ''; $('content').dispatchEvent(new Event('input')); eventLog('消息已提交，等待服务器确认');}
});
$('content').addEventListener('input', event => {$('byte-count').textContent = `${encoder.encode(event.target.value).length} / 4096 字节`;});
$('content').addEventListener('keydown', event => {if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {event.preventDefault(); $('send').click();}});
$('clear-events').addEventListener('click', () => {$('events').replaceChildren(); const empty = document.createElement('div'); empty.className='event-empty'; empty.textContent='等待新的活动…'; $('events').append(empty);});
updateUI();
