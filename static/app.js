function decodeJwtPayload(t){try{const b=t.split('.')[1];return JSON.parse(atob(b.replace(/-/g,'+').replace(/_/g,'/')))}catch(e){return {}}}
const API = {
  login: '/api/login',
  register: '/api/register',
  me: '/api/me',
  investments: '/api/investments',
  transactions: '/api/transactions',
  overview: '/api/portfolio/overview'
};

let token = localStorage.getItem('token') || null;
const authSection = document.getElementById('auth-section');
const dashboard = document.getElementById('dashboard');
const welcome = document.getElementById('welcome');
const authInfo = document.getElementById('auth-info');

function setAuth(tkn, user) {
  token = tkn;
  if (tkn) localStorage.setItem('token', tkn);
  authSection.classList.add('hidden');
  dashboard.classList.remove('hidden');
  authInfo.classList.remove('hidden');
  welcome.textContent = `Hello, ${user.username}`;
  refreshAll();
}

function logout() {
  token = null;
  localStorage.removeItem('token');
  dashboard.classList.add('hidden');
  authInfo.classList.add('hidden');
  authSection.classList.remove('hidden');
}

// Helpers
async function apiGet(url) {
  const res = await fetch(url, { headers: { 'Authorization': `Bearer ${token}` } });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
async function apiSend(url, method, body) {
  const res = await fetch(url, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function tryAuthFromToken() {
  if (!token) return;
  try {
    const me = await apiGet(API.me);
    setAuth(token, me);
  } catch { logout(); }
}

// Login
document.getElementById('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;
  const res = await fetch(API.login, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) });
  const data = await res.json();
  if (!res.ok) { alert(data.error || 'Login failed'); return; }

  token = data.access_token;

  // Try /api/me first, fallback to decoded token
  try {
    const me = await apiGet(API.me);
    setAuth(token, me);
  } catch (err) {
    const payload = decodeJwtPayload(token);
    const fallbackUser = { id: payload.sub, username: payload.username || username };
    setAuth(token, fallbackUser);
  }
});

document.getElementById('registerForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const username = document.getElementById('rusername').value.trim();
  const password = document.getElementById('rpassword').value;
  const res = await fetch(API.register, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) });
  const data = await res.json();
  if (!res.ok) { alert(data.error || 'Registration failed'); return; }
  alert('Registered! You can now log in.');
});

document.getElementById('logoutBtn').addEventListener('click', logout);

// Investments
const invForm = document.getElementById('invForm');
const invReset = document.getElementById('invReset');
const invTableBody = document.querySelector('#invTable tbody');
const txInvSelect = document.getElementById('tx_inv');
const refreshBtn = document.getElementById('refreshBtn');

function fillInvForm(inv) {
  document.getElementById('inv_id').value = inv ? inv.id : '';
  document.getElementById('inv_type').value = inv ? inv.type : 'stock';
  document.getElementById('inv_symbol').value = inv ? (inv.symbol || '') : '';
  document.getElementById('inv_name').value = inv ? inv.name : '';
  document.getElementById('inv_price').value = inv ? inv.current_price : '';
}

invReset.addEventListener('click', () => fillInvForm(null));

invForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const id = document.getElementById('inv_id').value;
  const body = {
    type: document.getElementById('inv_type').value,
    symbol: document.getElementById('inv_symbol').value || null,
    name: document.getElementById('inv_name').value.trim(),
    current_price: parseFloat(document.getElementById('inv_price').value)
  };
  try {
    if (id) await apiSend(`${API.investments}/${id}`, 'PUT', body);
    else await apiSend(API.investments, 'POST', body);
    fillInvForm(null);
    await refreshAll();
  } catch (e) { alert('Save failed: ' + e.message); }
});

refreshBtn.addEventListener('click', refreshAll);

async function renderInvestments() {
  const invs = await apiGet(API.investments);
  invTableBody.innerHTML = '';
  txInvSelect.innerHTML = '<option value="" disabled selected>Select investment</option>';
  invs.forEach(inv => {
    const tr = document.createElement('tr');
    const plClass = inv.unrealized_pl >= 0 ? 'pl-pos' : 'pl-neg';
    tr.innerHTML = `
      <td>${inv.type}</td>
      <td>${inv.symbol ?? ''}</td>
      <td>${inv.name}</td>
      <td>${inv.quantity.toFixed(4)}</td>
      <td>${inv.avg_purchase_price.toFixed(2)}</td>
      <td>${inv.current_price.toFixed(2)}</td>
      <td>${inv.current_value.toFixed(2)}</td>
      <td class="${plClass}">${inv.unrealized_pl.toFixed(2)}</td>
      <td class="${plClass}">${inv.pl_percent.toFixed(2)}%</td>
      <td>
        <button data-edit="${inv.id}">Edit</button>
        <button data-del="${inv.id}">Delete</button>
      </td>
    `;
    invTableBody.appendChild(tr);
    const opt = document.createElement('option');
    opt.value = inv.id;
    opt.textContent = `${inv.symbol ? inv.symbol + ' – ' : ''}${inv.name}`;
    txInvSelect.appendChild(opt);
  });

  invTableBody.addEventListener('click', async (e) => {
    const id = e.target.getAttribute('data-edit');
    const del = e.target.getAttribute('data-del');
    if (id) {
      const invs = await apiGet(API.investments);
      const inv = invs.find(x => x.id == id);
      fillInvForm(inv);
    } else if (del) {
      if (!confirm('Delete this investment (and its transactions)?')) return;
      await apiSend(`${API.investments}/${del}`, 'DELETE');
      await refreshAll();
    }
  }, { once: true });
}

// Overview
const totalsDiv = document.getElementById('totals');
const byTypeDiv = document.getElementById('byType');

async function renderOverview() {
  const data = await apiGet(API.overview);
  const t = data.totals;
  totalsDiv.innerHTML = `
    <div class="row gap">
      <span class="badge">Total Value: ${t.current_value.toFixed(2)}</span>
      <span class="badge">Cost Basis: ${t.cost_basis.toFixed(2)}</span>
      <span class="badge ${t.unrealized_pl >= 0 ? 'pl-pos' : 'pl-neg'}">Unrealized P/L: ${t.unrealized_pl.toFixed(2)} (${t.pl_percent.toFixed(2)}%)</span>
    </div>
  `;
  byTypeDiv.innerHTML = '';
  Object.entries(data.by_type).forEach(([type, v]) => {
    const div = document.createElement('div');
    div.className = 'muted';
    div.textContent = `${type}: value ${v.current_value.toFixed(2)}, P/L ${v.unrealized_pl.toFixed(2)} (${v.pl_percent.toFixed(2)}%)`;
    byTypeDiv.appendChild(div);
  });
}

// Transactions
const txForm = document.getElementById('txForm');
const txTableBody = document.querySelector('#txTable tbody');
const txRefreshBtn = document.getElementById('txRefreshBtn');

txForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const investment_id = parseInt(document.getElementById('tx_inv').value);
  const type = document.getElementById('tx_type').value;
  const quantity = parseFloat(document.getElementById('tx_qty').value);
  const price = parseFloat(document.getElementById('tx_price').value);
  const dateLocal = document.getElementById('tx_date').value; // yyyy-MM-ddTHH:mm
  if (!investment_id || !dateLocal) { alert('Please fill all fields'); return; }
  const date = new Date(dateLocal);
  try {
    await apiSend(API.transactions, 'POST', { investment_id, type, quantity, price, date: date.toISOString() });
    document.getElementById('tx_qty').value = '';
    document.getElementById('tx_price').value = '';
    await refreshAll();
  } catch (e) { alert('Create transaction failed: ' + e.message); }
});

txRefreshBtn.addEventListener('click', renderTransactions);

async function renderTransactions() {
  const txs = await apiGet(API.transactions);
  txTableBody.innerHTML = '';
  txs.forEach(tx => {
    const tr = document.createElement('tr');
    const d = new Date(tx.date);
    tr.innerHTML = `
      <td>${d.toLocaleString()}</td>
      <td>${tx.investment_symbol ? tx.investment_symbol + ' – ' : ''}${tx.investment_name}</td>
      <td>${tx.type}</td>
      <td>${tx.quantity.toFixed(4)}</td>
      <td>${tx.price.toFixed(2)}</td>
    `;
    txTableBody.appendChild(tr);
  });
}

async function refreshAll() {
  await Promise.all([renderOverview(), renderInvestments(), renderTransactions()]);
}

tryAuthFromToken();
