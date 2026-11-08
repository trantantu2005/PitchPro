
/* PitchPro MIS3047 – Django JSON API */
'use strict';

const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;',
  '"': '&quot;', "'": '&#39;'
}[c]));
const money = n => new Intl.NumberFormat('vi-VN').format(Number(n || 0)) + ' đ';
const pad = n => String(n).padStart(2, '0');
const localDate = (d = new Date()) =>
  `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const addDay = (day, n) => {
  const d = new Date(`${day}T12:00:00`);
  d.setDate(d.getDate() + n);
  return localDate(d);
};
const minutes = t => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));
const fmtMinutes = m => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;

const statusNames = {
  booked: 'Đã đặt',
  using: 'Đang sử dụng',
  completed: 'Đã trả sân',
  cancelled: 'Đã hủy',
  draft: 'Nháp',
  awaiting: 'Chờ thanh toán',
  qr_pending: 'Chờ QR',
  paid: 'Đã thanh toán',
  approved: 'Đã duyệt',
  locked: 'Đã khóa sổ',
  pending: 'Chờ xử lý',
  resolved: 'Đã xử lý'
};

const tag = s =>
  `<span class="pill ${esc(s)}">${esc(statusNames[s] || s || '—')}</span>`;

let DB = null;
let page = 'dashboard';
let selectedDay = localDate();
let fieldFilter = 'all';
let invoiceFilter = 'all';
let pendingFilter = 'all';
let locked = false;
let toastTimeout = null;

function toast(message, error = false) {
  const t = $('#toast');
  t.textContent = message;
  t.className = 'toast' + (error ? ' error' : '');
  t.hidden = false;
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => t.hidden = true, 4200);
}

function csrf() {
  return decodeURIComponent(
    (document.cookie.match(/(?:^|; )csrftoken=([^;]*)/) || [])[1] || ''
  );
}

async function api(url, method = 'GET', body = null) {
  const init = {
    method,
    credentials: 'same-origin',
    cache: 'no-store',
    headers: { Accept: 'application/json' }
  };

  if (method !== 'GET') {
    init.headers['X-CSRFToken'] = csrf();
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body || {});
  }

  const r = await fetch('/api/' + url.replace(/^\//, ''), init);
  let json;
  try {
    json = await r.json();
  } catch {
    throw Error(`Server trả về lỗi HTTP ${r.status}`);
  }
  if (!r.ok) throw Error(json.error || `HTTP ${r.status}`);
  return json;
}

function b(id) {
  return DB.bookings.find(x => String(x.id) === String(id));
}
function inv(id) {
  return DB.invoices.find(x => String(x.id) === String(id));
}
function field(id) {
  return DB.fields.find(x => String(x.id) === String(id));
}
function invDay(x) {
  return x.bookingId
    ? b(x.bookingId)?.date || ''
    : x.createdAt?.slice(0, 10) || '';
}
function canUseDay(day) {
  return day === DB.today &&
    !DB.reconciliations.some(r => r.day === day && r.status === 'locked');
}
function canCancelDay(day) {
  return day >= DB.today &&
    !DB.reconciliations.some(r => r.day === day && r.status === 'locked');
}
function nowMinutes() {
  const d = new Date();
  return d.getHours() * 60 + d.getMinutes();
}

function canCancelBooking(bk, invoice) {
  return Boolean(bk && invoice &&
    bk.status === 'booked' &&
    invoice.status === 'draft' &&
    canCancelDay(bk.date) &&
    (bk.date > DB.today ||
     minutes(bk.start) > nowMinutes()));
}

let cancelDraft = null;

async function refresh() {
  DB = await api('state/');
  if (!selectedDay) selectedDay = DB.today;
  render();
}

function heading(text, subtitle, buttons = '') {
  return `<div class="heading">
    <div><h1>${esc(text)}</h1><p>${esc(subtitle)}</p></div>
    <div class="actions">${buttons}</div>
  </div>`;
}

function btn(label, action, id = '', cls = 'outline') {
  return `<button type="button" class="btn ${cls}"
    data-action="${esc(action)}" data-id="${esc(id)}">${label}</button>`;
}

function stat(label, value, foot = '') {
  return `<div class="stat">
    <label>${esc(label)}</label>
    <b>${esc(value)}</b>
    <small>${esc(foot)}</small>
  </div>`;
}

function formField(label, name, type = 'text', value = '', more = '') {
  return `<div class="field">
    <label for="f_${name}">${esc(label)}</label>
    <input id="f_${name}" name="${esc(name)}" type="${type}"
      value="${esc(value)}" ${more}>
  </div>`;
}

function selectField(label, name, options, selected = '') {
  return `<div class="field">
    <label for="f_${name}">${esc(label)}</label>
    <select id="f_${name}" name="${esc(name)}">
      ${options.map(([v, l]) => `<option value="${esc(v)}"
        ${String(v) === String(selected) ? 'selected' : ''}>
        ${esc(l)}
      </option>`).join('')}
    </select>
  </div>`;
}

function modal(title, content) {
  $('#modalTitle').textContent = title;
  $('#modalBody').innerHTML = content;
  $('#modal').hidden = false;
  $('#modalBody input:not([type=hidden]),#modalBody select')?.focus();
}

function modalForm(title, name, html, submit = 'Xác nhận') {
  modal(title, `<form id="${name}">
    ${html}
    <div class="modalactions">
      <button type="button" class="btn outline" data-action="close-modal">Đóng</button>
      <button class="btn" type="submit">${esc(submit)}</button>
    </div>
  </form>`);
}

function closeModal() {
  $('#modal').hidden = true;
  $('#modalBody').innerHTML = '';
}

function errorHandler(err) {
  console.error(err);
  toast(err.message || 'Thao tác không thành công.', true);
}

async function init() {
  try {
    const session = await api('session/');
    if (!session.authenticated) {
      window.location.replace('/');
      return;
    }
    const dashboard = session.role === 'Manager' ? '/quan-ly/' : '/nhan-vien/';
    if (!['Staff', 'Manager'].includes(session.role)) {
      window.location.replace(session.role === 'Customer' ? '/khach/' : '/');
      return;
    }
    if (window.location.pathname !== dashboard) {
      window.location.replace(dashboard);
      return;
    }
    await refresh();
  } catch (e) {
    $('#content').innerHTML = `<div class="panel">
      <h2>Chưa kết nối được Django</h2>
      <p>${esc(e.message)}</p>
      <p>Hãy chạy <code>CHAY_WINDOWS.bat</code> ở thư mục dự án
      rồi mở trang được in trong Terminal.</p>
    </div>`;
  }
}

function render() {
  if (!DB) {
    window.location.replace('/');
    return;
  }

  const names = {
    dashboard: 'Bảng điều khiển',
    schedule: 'Lịch & đặt sân',
    invoices: 'Hóa đơn',
    inventory: 'Kho & dịch vụ',
    recon: 'Đối soát cuối ngày',
    audit: 'Nhật ký thao tác'
  };

  $('#pageName').textContent = names[page] || names.dashboard;
  $('#userDisplay').textContent =
    DB.user.name + (DB.user.manager ? ' · Quản lý' : ' · Nhân viên');
  $('#logoutBtn').hidden = false;

  $$('.sidebar nav a').forEach(a =>
    a.classList.toggle('active', a.dataset.page === page)
  );

  const content = {
    dashboard: dashboardPage,
    schedule: schedulePage,
    invoices: invoicePage,
    inventory: inventoryPage,
    recon: reconPage,
    audit: auditPage
  }[page] || dashboardPage;

  $('#content').innerHTML = content();
}

function dashboardPage() {
  const day = DB.today;
  const dayBooks = DB.bookings.filter(x => x.date === day);
  const receipts = DB.invoices.flatMap(i => i.receipts)
    .filter(x => x.status === 'success' &&
      x.createdAt?.slice(0, 10) === day);

  const pendingCount = DB.invoices.filter(x =>
    ['awaiting', 'qr_pending'].includes(x.status) ||
    (x.status === 'draft' && x.bookingId &&
      (b(x.bookingId)?.status === 'completed' ||
      (b(x.bookingId)?.status === 'cancelled' && x.collected > 0)))
  ).length;

  return heading('Tổng quan hoạt động',
    'Dữ liệu vận hành được lấy trực tiếp từ SQLite',
    btn('+ Đặt sân', 'booking', '', '') +
    btn('Lịch sân', 'goto', 'schedule', 'outline')) +
  `<div class="gridstats">
    ${stat('Lượt đặt hôm nay',
      dayBooks.filter(x => x.status !== 'cancelled').length,
      'Không tính lượt đã hủy')}
    ${stat('Đang sử dụng sân',
      dayBooks.filter(x => x.status === 'using').length,
      'Khách đang chơi')}
    ${stat('Khoản thu đã xác nhận',
      money(receipts.reduce((s, x) => s + x.amount, 0)),
      'Tiền mặt và chuyển khoản')}
    ${stat('Hóa đơn cần xử lý', pendingCount,
      'Gồm chờ thanh toán và xử lý cọc')}
  </div>
  <div class="twocol">
    <div class="panel">
      <h2>Lịch sử dụng sân hôm nay</h2>
      <div class="tablebox"><table>
        <thead><tr>
          <th>Sân</th><th>Đội bóng</th><th>Giờ</th>
          <th>Trạng thái</th><th></th>
        </tr></thead>
        <tbody>
          ${dayBooks.slice()
            .sort((a, b) => a.start.localeCompare(b.start))
            .map(x => `<tr>
              <td><b>${esc(field(x.pitchId)?.name)}</b></td>
              <td>${esc(x.name)}</td>
              <td>${esc(x.start)}–${esc(x.end)}</td>
              <td>${tag(x.status)}</td>
              <td>${btn('Xem','view-invoice',x.invoiceId,'outline small')}</td>
            </tr>`).join('') ||
            '<tr><td colspan="5">Chưa có lượt</td></tr>'}
        </tbody>
      </table></div>
    </div>
    <div class="panel">
      <h2>Hoạt động gần đây</h2>
      ${DB.audits.slice(0, 8).map(x =>
        `<div class="auditline">${esc(x.detail)}
          <small>${esc(x.actor)} ·
            ${esc(new Date(x.time).toLocaleString('vi-VN'))}</small>
        </div>`).join('') ||
        '<p class="muted">Chưa có hoạt động</p>'}
    </div>
  </div>`;
}

function schedulePage() {
  const today = DB.today;
  const bs = DB.bookings
    .filter(x => x.date === selectedDay)
    .sort((a, b) => a.start.localeCompare(b.start));

  const fields = DB.fields.filter(f =>
    f.active && (fieldFilter === 'all' || String(f.type) === fieldFilter)
  );

  return heading('Lịch sân trực tuyến',
    'Bấm vào lịch để thao tác; bấm ô trống để đặt sân',
    btn('+ Đặt sân','booking','','') +
    btn('Bán hàng nhanh','sale','','soft')) +
  `<div class="schedulelayout">
    <div class="schedleft">
      <div class="daystrip">
        ${Array.from({length: 7}, (_, i) => {
          const day = addDay(selectedDay, i - 3);
          return `<button class="day ${day === selectedDay ? 'active' : ''}"
            data-action="day" data-id="${day}">
            <span>${day === today ? 'Hôm nay' :
              new Date(day + 'T12:00:00')
                .toLocaleDateString('vi-VN',{weekday:'short'})}</span>
            <strong>${day.slice(8)}/${day.slice(5,7)}</strong>
          </button>`;
        }).join('')}
      </div>
      <div class="toolbar">
        <div class="filters">
          ${[['all','Tất cả sân'],['5','Sân 5 người'],['7','Sân 7 người']]
            .map(([k,l]) =>
              `<button class="filter ${fieldFilter === k ? 'active' : ''}"
                data-action="field-filter" data-id="${k}">${l}</button>`
            ).join('')}
        </div>
        <input class="dateinput" type="date" id="dateSchedule"
          value="${selectedDay}">
      </div>
      ${timeline(fields,bs)}
      <div class="fieldcards">
        ${fields.map(f => pitchCard(f,bs)).join('')}
      </div>
    </div>
    ${pendingPanel()}
  </div>`;
}

function timeline(fields, bs) {
  const H = 36, start = 6 * 60, end = 23 * 60;

  return `<div class="timeline">
    <div class="timelabel">Lưới lịch theo giờ · 06:00–23:00</div>
    <div class="timescroll" id="timescroll">
      <div class="timegrid"
        style="grid-template-columns:50px repeat(${fields.length},minmax(103px,1fr));min-width:${50+fields.length*103}px">
        <div class="timehead">GIỜ</div>
        ${fields.map(f =>
          `<div class="timehead">${esc(f.name)}</div>`).join('')}
        <div class="timeaxis">
          ${Array.from({length:18},(_,i) =>
            `<div class="hour" style="top:${i*H}px">
              ${pad(i+6)}:00
            </div>`).join('')}
        </div>
        ${fields.map(f => `<div class="timetrack">
          ${(selectedDay >= DB.today &&
            !DB.reconciliations.some(r =>
              r.day === selectedDay && r.status === 'locked'))
            ? Array.from({length:34},(_,i) =>
              `<button class="slot"
                style="top:${i*H/2}px"
                title="Đặt ${esc(f.name)}"
                data-action="slot"
                data-id="${f.id}|${start+i*30}"></button>`
              ).join('')
            : ''}
          ${bs.filter(x =>
            x.pitchId === f.id &&
            ['booked','using'].includes(x.status)
          ).map(x => {
            const top = Math.max(0,
              (minutes(x.start)-start)/60*H);
            const height = Math.max(19,
              (Math.min(end,minutes(x.end)) -
                Math.max(start,minutes(x.start)))/60*H);
            if (minutes(x.end) <= start ||
                minutes(x.start) >= end) return '';
            return `<button class="reservation ${esc(x.status)}"
              style="top:${top}px;height:${height}px"
              data-action="view-booking"
              data-id="${x.id}" title="${esc(x.name)}">
              <b>${esc(x.name)}</b>
              <small>${esc(x.start)}–${esc(x.end)}</small>
            </button>`;
          }).join('')}
        </div>`).join('')}
      </div>
    </div>
  </div>`;
}

function pitchCard(f, bs) {
  const entries = bs.filter(x =>
    x.pitchId === f.id &&
    ['booked','using'].includes(x.status));
  const active = entries.find(x => x.status === 'using');
  const next = entries.find(x => x.status === 'booked');
  const first = active || next;
  const now = nowMinutes();

  return `<div class="fieldcard">
    <small>SÂN ${esc(f.type)} NGƯỜI</small>
    <h3>${esc(f.name)}</h3>
    ${active ? tag('using') :
      next ? tag('booked') :
      '<span class="pill paid">Trống · Sẵn sàng</span>'}
    <p>${first
      ? `${esc(first.name)} · ${esc(first.start)}–${esc(first.end)}`
      : 'Sẵn sàng phục vụ'}</p>
    <div class="actions">
      ${active && canUseDay(active.date)
        ? btn('Trả sân','checkout',active.id,'small') : ''}
      ${active && canUseDay(active.date)
        ? btn('+ Dịch vụ','sale',active.invoiceId,'soft small') : ''}
      ${next && canUseDay(next.date)
        ? `<button data-action="checkin" data-id="${next.id}"
          class="btn small"
          ${now < minutes(next.start) || now >= minutes(next.end)
            ? 'disabled' : ''}>Nhận sân</button>`
        : ''}
      ${canCancelBooking(next, inv(next?.invoiceId))
        ? btn('Hủy sân','cancel-booking',next.id,'outline small')
        : ''}
      ${first
        ? btn('Chi tiết','view-booking',first.id,'outline small') : ''}
      ${selectedDay >= DB.today
        ? btn('+ Đặt','booking',f.id,'outline small') : ''}
    </div>
  </div>`;
}

function pendingPanel() {
  let list = DB.invoices.filter(i => {
    const bk = i.bookingId ? b(i.bookingId) : null;
    const stillServing = i.status === 'draft' &&
      bk?.status === 'completed';
    const waitingForPayment =
      ['awaiting','qr_pending'].includes(i.status);
    const cancellationReview =
      i.status === 'draft' &&
      bk?.status === 'cancelled' &&
      i.collected > 0;

    return invDay(i) === selectedDay &&
      (stillServing || waitingForPayment || cancellationReview);
  });

  if (pendingFilter === 'team')
    list = list.filter(i => i.bookingId);
  if (pendingFilter === 'retail')
    list = list.filter(i => !i.bookingId);

  const recent = DB.invoices.filter(i =>
    i.status === 'paid' &&
    invDay(i) === selectedDay
  ).slice(0,3);

  return `<div class="panel pendingpanel">
    <h2>Hóa đơn cần xử lý
      <span class="pill pending">${list.length}</span>
    </h2>
    <div class="filters" style="margin-bottom:10px">
      ${[['all','Tất cả'],['team','Đội bóng'],['retail','Khách lẻ']]
        .map(([key,label]) =>
          `<button data-action="pending-filter"
            data-id="${key}"
            class="filter ${pendingFilter === key ? 'active' : ''}">
            ${label}</button>`
        ).join('')}
    </div>
    <div class="pendinglist">
      ${list.map(i => {
        const bk = i.bookingId ? b(i.bookingId) : null;
        const cancelled = bk?.status === 'cancelled';
        return `<div class="pendingcard">
          <strong>${esc(i.customer)}</strong>
          <div class="sub">
            HĐ-${i.id} ·
            ${esc(field(bk?.pitchId)?.name || 'Bán lẻ')}
          </div>
          ${cancelled && i.status === 'draft'
            ? '<span class="pill pending">Đã hủy · Chờ xử lý cọc</span>'
            : i.status === 'draft'
              ? '<span class="pill using">Đã trả sân · Đang phục vụ</span>'
              : tag(i.status)}
          <div class="total">
            ${cancelled
              ? 'Cọc đã nhận ' + money(i.collected)
              : 'Còn thu ' + money(i.due)}
          </div>
          ${cancelled
            ? btn('Xem hóa đơn','view-invoice',i.id,'outline small')
            : i.status === 'draft'
              ? btn('+ Dịch vụ','sale',i.id,'soft small') +
                btn('Chốt hóa đơn','finalize-invoice',i.id,'small')
              : btn('Thanh toán','pay-picker',i.id,'')}
        </div>`;
      }).join('') ||
        '<div class="empty">Không có hóa đơn cần xử lý.</div>'}
      ${recent.length
        ? '<div style="grid-column:1/-1;font-size:11px;color:#638776;font-weight:800;margin-top:10px">ĐÃ THANH TOÁN GẦN ĐÂY</div>'
        : ''}
      ${recent.map(i => `<div class="pendingcard">
        <strong>${esc(i.customer)}</strong>
        <div class="sub">HĐ-${i.id}</div>
        <div class="total">Đã thu ${money(i.collected)}</div>
        ${btn('Xem hóa đơn','view-invoice',i.id,'outline small')}
      </div>`).join('')}
    </div>
  </div>`;
}

function invoicePage() {
  let list = DB.invoices;
  if (invoiceFilter !== 'all')
    list = list.filter(i => i.status === invoiceFilter);

  const pending = DB.invoices.filter(i => {
    const bk = i.bookingId ? b(i.bookingId) : null;
    return ['awaiting','qr_pending'].includes(i.status) ||
      (i.status === 'draft' &&
       (bk?.status === 'completed' ||
        (bk?.status === 'cancelled' && i.collected > 0)));
  });

  return heading('Quản lý hóa đơn',
    'Tra cứu hóa đơn và lịch sử thanh toán') +
  `<div class="gridstats">
    ${stat('Tổng hóa đơn',DB.invoices.length)}
    ${stat('Đã thanh toán',
      DB.invoices.filter(x => x.status === 'paid').length)}
    ${stat('Hóa đơn cần xử lý',pending.length)}
    ${stat('Tổng tiền hóa đơn đã thu',
      money(DB.invoices.filter(x => x.status === 'paid')
        .reduce((s,x) => s + x.collected,0)))}
  </div>
  <div class="toolbar"><div class="filters">
    ${[['all','Tất cả'],['paid','Đã thanh toán'],
       ['awaiting','Chờ thanh toán'],['qr_pending','Chờ QR'],
       ['draft','Nháp']]
      .map(([k,l]) =>
        `<button class="filter ${invoiceFilter === k ? 'active' : ''}"
          data-action="invoice-filter" data-id="${k}">
          ${l}</button>`).join('')}
  </div></div>
  <div class="panel tablebox"><table>
    <thead><tr>
      <th>Mã</th><th>Khách/Đội bóng</th><th>Loại</th>
      <th>Tổng tiền</th><th>Đã thu</th><th>Còn thu</th>
      <th>Trạng thái</th><th></th>
    </tr></thead><tbody>
      ${list.map(i => {
        const bk = i.bookingId ? b(i.bookingId) : null;
        return `<tr>
          <td><b>HD-${i.id}</b></td>
          <td>${esc(i.customer)}</td>
          <td>${i.bookingId ? 'Thuê sân' : 'Bán lẻ'}</td>
          <td>${money(i.total)}</td>
          <td>${money(i.collected)}</td>
          <td>${bk?.status === 'cancelled'
            ? 'Chờ xử lý' : money(i.due)}</td>
          <td>${i.status === 'draft' &&
                 bk?.status === 'cancelled'
            ? '<span class="pill pending">Đã hủy · Chờ xử lý cọc</span>'
            : i.status === 'draft' &&
              bk?.status === 'completed'
              ? '<span class="pill using">Đã trả sân · Đang phục vụ</span>'
              : tag(i.status)}</td>
          <td>${btn('Xem','view-invoice',i.id,'outline small')}</td>
        </tr>`;
      }).join('') ||
        '<tr><td colspan="8">Không có hóa đơn.</td></tr>'}
    </tbody>
  </table></div>`;
}

function inventoryPage() {
  const list = DB.products.filter(p => p.active);
  return heading('Kho hàng & dịch vụ',
    'Tồn kho đồng bộ trực tiếp với SQLite',
    btn('+ Sản phẩm mới','product-create','','soft') +
    btn('+ Nhập hàng','restock','','')) +
  `<div class="panel tablebox"><table>
    <thead><tr>
      <th>Sản phẩm / Dịch vụ</th>
      <th>Đơn giá</th><th>Đơn vị</th>
      <th>Số lượng tồn</th><th>Trạng thái</th>
    </tr></thead>
    <tbody>
      ${list.map(p => `<tr>
        <td><b>${esc(p.name)}</b></td>
        <td>${money(p.price)}</td>
        <td>${esc(p.unit)}</td>
        <td>${p.tracksStock
          ? Number(p.stock).toLocaleString('vi-VN')
          : 'Không quản lý tồn'}</td>
        <td>${!p.tracksStock
          ? '<span class="pill paid">Dịch vụ</span>'
          : p.stock <= 10 ? tag('pending')
          : '<span class="pill paid">Sẵn sàng</span>'}</td>
      </tr>`).join('') ||
        '<tr><td colspan="5">Chưa có sản phẩm.</td></tr>'}
    </tbody>
  </table></div>`;
}

function reconPage() {
  return window.PitchProReconciliation.page();
}
async function fillRecon() {
  return window.PitchProReconciliation.fill();
}

function auditPage() {
  return heading('Nhật ký thao tác',
    'Lịch sử hành động được lưu ở SQLite') +
  `<div class="panel">
    ${DB.audits.map(x => `<div class="auditline">
      <b>${esc(x.event)}</b> — ${esc(x.detail)}
      <small>${esc(x.actor)} ·
        ${esc(new Date(x.time).toLocaleString('vi-VN'))}</small>
    </div>`).join('') || '<p>Chưa có nhật ký.</p>'}
  </div>`;
}

function bookingModal(pitch = '', date = selectedDay, start = '17:00') {
  const end = fmtMinutes(Math.min(23*60+59,minutes(start)+90));
  modalForm('Tạo lượt đặt sân','bookingForm',
    `<div class="formgrid">
      ${selectField('Sân','pitchId',
        DB.fields.filter(f => f.active)
          .map(f => [f.id,`${f.name} · ${f.type} người`]),pitch)}
      ${formField('Ngày sử dụng','date','date',date,
        'required min="'+DB.today+'"')}
      ${formField('Giờ bắt đầu','start','time',start,'required')}
      ${formField('Giờ kết thúc','end','time',end,'required')}
      ${formField('Khách / đội bóng','name','text','',
        'required maxlength="150"')}
      ${formField('Số điện thoại','phone','tel','',
        'required maxlength="20"')}
      ${selectField('Tỷ lệ cọc yêu cầu','depositRate',
        [[0,'Không cọc'],[40,'40%'],[50,'50%'],[60,'60%']],0)}
    </div>`,
    'Xác nhận đặt sân');
}

function saleModal(target = '') {
  const options = [
    ['retail','Khách lẻ · Hóa đơn riêng'],
    ...DB.invoices.filter(i =>
      i.status === 'draft' &&
      i.bookingId &&
      ['using','completed'].includes(b(i.bookingId)?.status) &&
      invDay(i) === DB.today
    ).map(i => [
      i.id,
      `${field(b(i.bookingId)?.pitchId)?.name || 'Sân'} ·
       ${i.customer} (HĐ-${i.id})`
    ])
  ];

  modalForm('Bán hàng nhanh','saleForm',
    selectField('Gộp vào sân / hóa đơn','invoice',
      options,target || 'retail') +
    selectField('Sản phẩm / dịch vụ','productId',
      DB.products.filter(p => p.active).map(p => [
        p.id,
        `${p.name} · ${money(p.price)}${
          p.tracksStock ? ' · còn ' + p.stock : ''}`
      ])) +
    formField('Số lượng','quantity','number',1,
      'min="1" max="1000" required'),
    'Thêm sản phẩm');
}

function invoiceModal(id) {
  const i = inv(id);
  if (!i) throw Error('Hóa đơn không tồn tại');
  const booking = i.bookingId ? b(i.bookingId) : null;
  const cancelled = booking?.status === 'cancelled';

  const canAdd = i.status === 'draft' && booking &&
    ['using','completed'].includes(booking.status) &&
    canUseDay(booking.date);

  const canFinalize = i.status === 'draft' &&
    booking?.status === 'completed' &&
    canUseDay(booking.date);

  modal('Hóa đơn HD-'+i.id,
    `<div class="hint">
      <b>${esc(i.customer)}</b>
      <div>${booking
        ? `${esc(field(booking.pitchId)?.name)} ·
          ${esc(booking.date)}
          ${esc(booking.start)}–${esc(booking.end)}`
        : 'Khách lẻ'}</div>
      <div>
        ${tag(i.status)}
        ${booking?.status === 'completed' && i.status === 'draft'
          ? '<span class="pill using">Đã trả sân · Đang phục vụ</span>'
          : ''}
        ${cancelled
          ? '<span class="pill pending">Đã hủy</span>'
          : ''}
      </div>
    </div>` +
    (cancelled && i.status === 'draft'
      ? `<div class="hint warn">
        Lịch đã hủy. Có ${money(i.collected)} đã thu cần chủ sân
        xem xét. Tiền chưa được hoàn và không tiếp tục thu tiền
        trên hóa đơn này.
      </div>` : '') +
    i.items.map(x => `<div class="billrow">
      <span>${esc(x.name)} × ${x.qty}</span>
      <b>${money(x.qty*x.unitPrice)}</b>
    </div>`).join('') +
    `<div class="billrow total">
      <span>Tổng tiền</span><b>${money(i.total)}</b>
    </div>
    <div class="billrow">
      <span>Đã nhận cọc/thanh toán</span>
      <b>${money(i.collected)}</b>
    </div>
    <div class="billrow">
      <span>${cancelled
        ? 'Khoản còn thu (không thu tiếp)' : 'Còn phải thu'}</span>
      <b>${cancelled ? 'Chờ quyết định' : money(i.due)}</b>
    </div>` +
    (i.receipts.length
      ? `<h4>Khoản thu đã ghi nhận</h4>` +
        i.receipts.map(x => `<div class="billrow">
          <span>${
            x.type === 'deposit' ? 'Tiền cọc' :
            x.type === 'settlement' ? 'Thanh toán' : 'Hoàn tiền'
          } · ${x.method === 'cash' ? 'Tiền mặt' : 'Chuyển khoản'}
          · ${esc(x.reference)}</span>
          <b>${money(x.amount)} ${tag(x.status)}</b>
        </div>`).join('')
      : '') +
    `<div class="modalactions">` +
    (i.status === 'draft' && booking &&
     ['booked','using'].includes(booking.status) &&
     booking.depositRate > 0
      ? btn('Thu cọc','deposit',i.id,'outline') : '') +
    (canAdd ? btn('+ Dịch vụ','sale',i.id,'soft') : '') +
    (canFinalize
      ? btn('Chốt hóa đơn','finalize-invoice',i.id,'') : '') +
    (['awaiting','qr_pending'].includes(i.status)
      ? btn('Thanh toán','pay-picker',i.id,'') : '') +
    (canCancelBooking(booking, i)
      ? btn('Hủy sân','cancel-booking',booking.id,'outline') : '') +
    btn('Đóng','close-modal','','outline') +
    `</div>`);
}

function payPicker(id) {
  const i = inv(id);
  if (!i || !['awaiting','qr_pending'].includes(i.status))
    throw Error('Hóa đơn không còn chờ thanh toán');

  modal('Thanh toán',
    `<div style="text-align:center;padding:15px 0">
      <div class="muted">${esc(i.customer)} · HD-${i.id}</div>
      <p>Số tiền cần thu</p>
      <strong style="font-size:30px;color:#14744d">
        ${money(i.due)}
      </strong>
    </div>
    <div class="modalactions">
      ${btn('Tiền mặt','pay-cash',i.id,'')}
      ${btn('Mã QR','pay-qr',i.id,'soft')}
    </div>
    <div class="hint warn">
      Chỉ xác nhận khi tiền thực sự đã được nhận.
      QR là mã tham chiếu mô phỏng, không phải VietQR ngân hàng.
    </div>`);
}

function qrModal(id) {
  const i = inv(id);
  if (!i) throw Error('Không thấy hóa đơn');
  const p = i.receipts.find(x => x.status === 'pending');

  modal('Thanh toán bằng QR (mô phỏng)',
    `<div style="text-align:center">
      <p><strong>${money(i.due)}</strong></p>
      <img class="qrpreview" src="/api/invoices/${i.id}/qr/image/"
        alt="QR tham chiếu hóa đơn">
      <p style="font-size:12px">
        ${esc(p?.reference || 'Đang tạo mã')}
      </p>
    </div>
    <div class="hint warn">
      QR này chứa mã tham chiếu để demo, không liên kết với
      tài khoản ngân hàng. Chỉ xác nhận sau khi đối chiếu
      khoản chuyển thực tế.
    </div>
    ${formField('Mã giao dịch ngân hàng sau khi kiểm tra',
      'bankReference','text','','minlength="5"')}
    <label style="font-size:12px">
      <input id="verifiedBank" type="checkbox">
      Tôi đã đối chiếu chứng từ chuyển khoản
    </label>
    <div class="modalactions">
      ${btn('Quay lại','pay-picker',i.id,'outline')}
      ${btn('Xác nhận đã nhận chuyển khoản','pay-bank',i.id,'')}
    </div>`);
}

function paidModal(id) {
  const i = inv(id);
  modal('Thanh toán thành công',
    `<div style="text-align:center;padding:20px 0">
      <div style="font-size:40px;color:#188256">✓</div>
      <b>${esc(i.customer)}</b>
      <p class="money" style="font-size:26px">
        ${money(i.total)}
      </p>
      <div class="muted">
        HD-${i.id} · Đã ghi nhận vào SQLite
      </div>
    </div>
    <div class="modalactions">
      ${btn('Xem hóa đơn','view-invoice',i.id,'')}
      ${btn('Đóng','close-modal','','outline')}
    </div>`);
}

function bookingDetails(id) {
  const x = b(id), i = inv(x?.invoiceId);
  if (!x || !i) throw Error('Không tìm thấy lượt sân');

  const isToday = canUseDay(x.date);
  const canStart = isToday && x.status === 'booked' &&
    nowMinutes() >= minutes(x.start) &&
    nowMinutes() < minutes(x.end);
  const canAdd = isToday && i.status === 'draft' &&
    ['using','completed'].includes(x.status);
  const canFinalize = isToday && i.status === 'draft' &&
    x.status === 'completed';

  modal('Lượt đặt · '+esc(field(x.pitchId)?.name),
    `<div class="hint">
      <b>${esc(x.name)}</b>
      <div>${esc(x.date)} ·
        ${esc(x.start)}–${esc(x.end)}</div>
      <div>${tag(x.status)} ${tag(i.status)}</div>
    </div>
    <div class="billrow">
      <span>Tiền sân và sản phẩm</span>
      <b>${money(i.total)}</b>
    </div>
    <div class="billrow">
      <span>Còn phải thu</span>
      <b>${money(i.due)}</b>
    </div>
    <div class="modalactions">
      ${canStart ? btn('Nhận sân','checkin',x.id,'') : ''}
      ${canAdd ? btn('+ Dịch vụ','sale',i.id,'soft') : ''}
      ${x.status === 'using' && isToday
        ? btn('Trả sân','checkout',x.id,'') : ''}
      ${canFinalize
        ? btn('Chốt hóa đơn','finalize-invoice',i.id,'') : ''}
      ${x.status === 'booked' && x.depositRate > 0
        ? btn('Thu cọc','deposit',i.id,'outline') : ''}
      ${canCancelBooking(x, i)
        ? btn('Hủy sân','cancel-booking',x.id,'outline') : ''}
      ${btn('Xem hóa đơn','view-invoice',i.id,'outline')}
    </div>`);
}

function cancellationModal(id) {
  const bk = b(id), i = inv(bk?.invoiceId);

  if (!canCancelBooking(bk, i))
    throw Error('Lượt sân không đủ điều kiện hủy.');

  const draft = cancelDraft?.id === String(id)
    ? cancelDraft : null;

  modal('Xử lý yêu cầu hủy sân',
    `<div class="hint">
      <b>${esc(bk.name)} · ${esc(field(bk.pitchId)?.name)}</b>
      <div>${esc(bk.date)} ${esc(bk.start)}–${esc(bk.end)}</div>
      <div>HD-${i.id} · Đã nhận: ${money(i.collected)}</div>
    </div>` +

    `<div class="hint warn">
      Hủy lịch khác hoàn tiền. Hệ thống áp dụng quy tắc hủy sân;
      chủ sân xem xét và xử lý tiền cọc riêng.
    </div>` +

    `<div class="field">
      <label>Loại lý do hủy</label>
      <select id="cancelReasonType">
        <option value="personal"
          ${draft?.reasonType==='personal'?'selected':''}>
          Cá nhân / đổi kế hoạch
        </option>
        <option value="weather"
          ${draft?.reasonType==='weather'?'selected':''}>
          Thời tiết chưa xác minh
        </option>
        <option value="other"
          ${draft?.reasonType==='other'?'selected':''}>
          Lý do khác
        </option>
      </select>
    </div>` +

    `<div class="field">
      <label>Lý do chi tiết (5–300 ký tự)</label>
      <textarea id="cancelReason" rows="4"
        maxlength="300">${esc(draft?.reason||'')}</textarea>
    </div>` +

    `<div class="modalactions">` +
    btn('Xác nhận hủy sân','cancel-manual',id,'') +
    btn('Đóng','close-modal','','outline') +
    `</div>`
  );
}

function readCancelInput(id) {
  const reason = ($('#cancelReason')?.value||'').trim();
  const reasonType = $('#cancelReasonType')?.value||'personal';

  if (reason.length < 5 || reason.length > 300)
    throw Error('Lý do hủy phải 5–300 ký tự.');

  cancelDraft = {
    id:String(id),
    reason,
    reasonType
  };

  return cancelDraft;
}

async function finishCancel(id, data) {
  if (!data || data.id !== String(id))
    throw Error('Thiếu lý do hủy.');

  if (!confirm(
    'Xác nhận hủy lịch? Tiền cọc KHÔNG tự động hoàn.'
  )) return;

  const bk = b(id);

  const result = await api(
    `bookings/${id}/cancel/`,
    'POST',
    {
      reason:data.reason,
      reasonType:data.reasonType
    }
  );

  cancelDraft = null;
  closeModal();
  selectedDay = bk.date;

  await refresh();

  toast(result.requiresRefundReview
    ? 'Đã hủy lịch; cần quản lý xem xét cọc/thời tiết.'
    : 'Đã hủy và giải phóng sân.');
}

// XỬ LÝ NÚT
async function action(which, id) {
  switch (which) {
    case 'close-modal':
      closeModal();
      break;

    case 'goto':
      location.hash = id;
      break;

    case 'day':
      selectedDay = id;
      render();
      break;

    case 'field-filter':
      fieldFilter = id;
      render();
      break;

    case 'invoice-filter':
      invoiceFilter = id;
      render();
      break;

    case 'pending-filter':
      pendingFilter = id;
      render();
      break;

    case 'booking':
      bookingModal(id);
      break;

    case 'slot': {
      const [f,m] = id.split('|');
      const mi = Number(m);
      if (selectedDay === DB.today && mi < nowMinutes())
        throw Error('Không thể đặt vào khung giờ đã qua.');
      bookingModal(f,selectedDay,fmtMinutes(mi));
      break;
    }

    case 'sale':
      saleModal(id);
      break;

    case 'view-invoice':
      invoiceModal(id);
      break;

    case 'view-booking':
      bookingDetails(id);
      break;

    case 'cancel-booking':
      cancellationModal(id);
      break;

    case 'cancel-manual':
      await finishCancel(id, readCancelInput(id));
      break;

    case 'checkin':
      await api(`bookings/${id}/check-in/`,'POST');
      closeModal();
      await refresh();
      toast('Đã nhận sân thành công.');
      break;

    case 'checkout': {
      const bk = b(id);
      if (!bk) throw Error('Không có lượt sân');
      const early = nowMinutes() < minutes(bk.end);

      if (early && !confirm(
        'Khách trả sân trước giờ dự kiến. Xác nhận trả sân sớm? ' +
        'Hóa đơn vẫn mở để gọi thêm dịch vụ.'
      )) return;

      await api(`bookings/${id}/check-out/`,'POST',{
        earlyCheckout:early
      });

      closeModal();
      selectedDay = DB.today;
      page = 'schedule';
      await refresh();
      toast('Đã trả sân. Khách có thể tiếp tục gọi nước và dịch vụ.');
      break;
    }

    case 'finalize-invoice': {
      if (!confirm('Khách đã dùng xong và yêu cầu thanh toán?')) return;

      const result = await api(
        `invoices/${id}/finalize/`,'POST'
      );
      closeModal();
      await refresh();

      if (result.invoice.status === 'paid')
        paidModal(id);
      else
        payPicker(id);
      break;
    }

    case 'pay-picker':
      payPicker(id);
      break;

    case 'pay-cash': {
      if (!confirm('Bạn đã nhận đủ tiền mặt và muốn hoàn tất thanh toán?'))
        return;

      const x = inv(id);
      if (x.status === 'qr_pending')
        await api(`invoices/${id}/qr/cancel/`,'POST');

      await api(`invoices/${id}/pay/`,'POST',{
        method:'cash'
      });
      await refresh();
      paidModal(id);
      break;
    }

    case 'pay-qr': {
      const x = inv(id);
      if (x.status === 'awaiting')
        await api(`invoices/${id}/qr/`,'POST');
      await refresh();
      qrModal(id);
      break;
    }

    case 'pay-bank': {
      const ref = $('#f_bankReference')?.value.trim();
      if (!$('#verifiedBank')?.checked)
        throw Error('Cần xác nhận đã kiểm tra sao kê hoặc giao dịch ngân hàng.');

      await api(`invoices/${id}/pay/`,'POST',{
        method:'bank',
        bankReference:ref,
        manuallyVerified:true
      });
      await refresh();
      paidModal(id);
      break;
    }

    case 'deposit': {
      const x = inv(id), bk = b(x.bookingId);

      const collected = x.receipts
        .filter(p => p.type === 'deposit' && p.status === 'success')
        .reduce((s,p) => s + p.amount,0);

      const rental = x.items
        .filter(p => p.name.startsWith('Thuê Sân') ||
                     p.name.startsWith('Thuê sân'))
        .reduce((s,p) => s + p.qty*p.unitPrice,0);

      const expected = Math.max(0,
        Math.round(rental*(bk?.depositRate || 0)/100) - collected
      );

      modalForm('Ghi nhận tiền cọc','depositForm',
        `<input type="hidden" name="invoiceId" value="${x.id}">` +
        formField('Số tiền cọc (VNĐ)','amount','number',
          expected,'required min="1"') +
        selectField('Phương thức','method',[
          ['cash','Tiền mặt'],
          ['bank','Chuyển khoản']
        ]) +
        formField('Mã tham chiếu khi chuyển khoản',
          'reference','text','',
          'placeholder="Chỉ điền khi chuyển khoản"'),
        'Xác nhận đã thu cọc');
      break;
    }

    case 'product-create': {
      modalForm('Thêm sản phẩm / dịch vụ mới','productForm',
        `<div class="formgrid">
          ${formField('Tên sản phẩm / dịch vụ','name','text','',
            'required maxlength="100"')}
          ${formField('Giá bán (VNĐ)','price','number',10000,
            'required min="0" max="1000000000" step="1"')}
          ${formField('Đơn vị tính','unit','text','chai',
            'required maxlength="20"')}
          ${selectField('Loại mặt hàng','tracksStock',[
            ['true','Hàng hóa · Theo dõi tồn'],
            ['false','Dịch vụ · Không theo dõi tồn']
          ],'true')}
          ${formField('Số lượng tồn ban đầu','stock','number',0,
            'required min="0" max="100000" step="1"')}
        </div>
        <div class="hint">Nếu chọn Dịch vụ, hãy để tồn ban đầu bằng 0.</div>`,
        'Tạo sản phẩm');
      break;
    }

    case 'restock': {
      const goods = DB.products.filter(p =>
        p.active && p.tracksStock);
      if (!goods.length)
        throw Error('Chưa có hàng hóa quản lý tồn. Hãy tạo sản phẩm mới trước.');

      modalForm('Nhập thêm hàng','restockForm',
        selectField('Sản phẩm','productId',
          goods.map(p => [p.id,
            `${p.name} · tồn hiện tại ${p.stock}`])) +
        formField('Số lượng nhập','quantity','number',1,
          'min="1" max="100000" step="1" required'),
        'Lưu nhập hàng');
      break;
    }

    case 'recon-load':
      await fillRecon();
      break;

    case 'recon-approve':
      if (!confirm('Quản lý phê duyệt kỳ đối soát này?')) return;
      await api(`reconciliation/${selectedDay}/approve/`,'POST');
      await refresh();
      await fillRecon();
      toast('Đã phê duyệt kỳ đối soát.');
      break;

    case 'recon-lock':
      if (!confirm(
        'Khóa sổ ngày '+selectedDay+'? Sau đó không thể chỉnh sửa giao dịch.'
      )) return;
      await api(`reconciliation/${selectedDay}/lock/`,'POST');
      await refresh();
      await fillRecon();
      toast('Đã khóa sổ.');
      break;

    case 'recon-resolve':
      modalForm('Giải trình ngoại lệ','resolveForm',
        `<div class="hint">
          Số thực tế phải được điều chỉnh khớp với sổ hệ thống
          trước khi giải quyết.
        </div>
        <div class="field">
          <label>Giải trình và chứng từ kiểm tra</label>
          <textarea name="resolution" required minlength="10"
            placeholder="Đã kiểm đếm lại và đối chiếu chứng từ..."></textarea>
        </div>`,
        'Xác nhận giải quyết');
      break;

    default:
      throw Error('Chức năng chưa hỗ trợ: '+which);
  }
}

// XỬ LÝ FORM
async function handleForm(form) {
  const d = Object.fromEntries(new FormData(form).entries());

  switch (form.id) {
    case 'bookingForm':
      await api('bookings/','POST',d);
      closeModal();
      await refresh();
      toast('Đặt sân thành công.');
      break;

    case 'saleForm': {
      const path = d.invoice === 'retail'
        ? 'invoices/retail/'
        : `invoices/${d.invoice}/items/`;

      await api(path,'POST',{
        productId:d.productId,
        quantity:Number(d.quantity)
      });
      closeModal();
      await refresh();
      toast('Đã thêm sản phẩm và cập nhật kho.');
      break;
    }

    case 'depositForm':
      await api(`invoices/${d.invoiceId}/deposit/`,'POST',{
        amount:Number(d.amount),
        method:d.method,
        reference:d.reference
      });
      closeModal();
      await refresh();
      toast('Đã lưu khoản cọc.');
      break;

    case 'productForm':
      await api('products/','POST',{
        name:d.name.trim(),
        unit:d.unit.trim(),
        price:Number(d.price),
        stock:Number(d.stock),
        tracksStock:d.tracksStock === 'true'
      });
      closeModal();
      await refresh();
      toast('Đã tạo sản phẩm mới và cập nhật danh mục bán hàng.');
      break;

    case 'restockForm': {
      const result = await api('stock/restock/','POST',{
        productId:d.productId,
        quantity:Number(d.quantity)
      });
      closeModal();
      await refresh();

      const shown = DB.products.find(p =>
        String(p.id) === String(d.productId));

      if (!shown || Number(shown.stock) !== Number(result.stock)) {
        throw Error('Máy chủ đã ghi nhận tồn '+result.stock+
          ' nhưng dữ liệu trang chưa đồng bộ. Kiểm tra API /api/state/.');
      }
      toast(`Nhập hàng thành công. Tồn kho mới: ${result.stock}.`);
      break;
    }

    case 'reconForm':
      await api('reconciliation/','POST',{
        date:selectedDay,
        countedCash:Number(d.countedCash),
        countedBank:Number(d.countedBank),
        notes:d.notes || ''
      });
      await refresh();
      await fillRecon();
      toast('Đã lưu đối soát.');
      break;

    case 'resolveForm':
      await api(`reconciliation/${selectedDay}/resolve/`,'POST',{
        resolution:d.resolution
      });
      closeModal();
      await refresh();
      await fillRecon();
      toast('Đã giải quyết ngoại lệ.');
      break;

    default:
      throw Error('Form chưa được hỗ trợ');
  }
}

// CÁC SỰ KIỆN
document.addEventListener('click',async e => {
  const target = e.target.closest('[data-action]');
  if (!target) return;
  e.preventDefault();
  if (target.disabled) return;
  try {
    await action(target.dataset.action,target.dataset.id || '');
  } catch (err) {
    errorHandler(err);
  }
});

document.addEventListener('submit',async e => {
  if (!e.target.matches('form')) return;
  e.preventDefault();
  const bt = e.target.querySelector('[type=submit]');
  if (bt) bt.disabled = true;
  try {
    await handleForm(e.target);
  } catch (err) {
    errorHandler(err);
  } finally {
    if (bt?.isConnected) bt.disabled = false;
  }
});

document.addEventListener('change',async e => {
  if (e.target.id === 'dateSchedule' ||
      e.target.id === 'dateRecon') {
    selectedDay = e.target.value;
    render();
    if (page === 'recon') await fillRecon();
  }
});

$('#modalClose').addEventListener('click',closeModal);
$('#modal').addEventListener('click',e => {
  if (e.target === $('#modal')) closeModal();
});
$('#menuToggle').addEventListener('click',() =>
  $('#sidebar').classList.toggle('open')
);

$('#logoutBtn').addEventListener('click',async () => {
  try {
    await api('session/','DELETE');
    DB = null;
    window.location.replace('/');
  } catch (e) {
    errorHandler(e);
  }
});

window.addEventListener('hashchange',() => {
  page = location.hash.slice(1) || 'dashboard';
  if (!['dashboard','schedule','invoices',
         'inventory','recon','audit'].includes(page))
    page = 'dashboard';

  $('#sidebar').classList.remove('open');
  if (DB) {
    render();
    if (page === 'recon')
      fillRecon().catch(errorHandler);
  }
});

(async () => {
  page = location.hash.slice(1) || 'dashboard';
  await init();
  if (DB && page === 'recon')
    fillRecon().catch(errorHandler);
})();
