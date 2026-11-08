/* PitchPro / Giai doan 2 - cong khach hang, khong su dung API state noi bo. */
'use strict';
const $ = (s, root = document) => root.querySelector(s);
const escapeHtml = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtMoney = n => new Intl.NumberFormat('vi-VN').format(Number(n || 0)) + ' đ';
const todayString = () => { const d=new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };
const toMinutes = t => Number(t.slice(0,2))*60+Number(t.slice(3,5));
const timeOptions = Array.from({length:35},(_,i) => {
  const m = 360+i*30; return `${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`;
});
let model = {session:null, customer:null, fields:[], bookings:[], selectedField:null, day:todayString(), busy:[], view:'find'};
function notification(message, error=false) {
  const e=$('#message');e.textContent=message;e.className='notice'+(error?' error':'');e.hidden=false;
  e.scrollIntoView({behavior:'smooth',block:'nearest'});
}
function clearNotification(){ $('#message').hidden=true; }
function csrf(){ return decodeURIComponent((document.cookie.match(/(?:^|; )csrftoken=([^;]*)/)||[])[1]||''); }
async function request(url, method='GET', body=undefined) {
  const options={method,credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}};
  if(method!=='GET') {
    options.headers['X-CSRFToken']=csrf();
    options.headers['Content-Type']='application/json';
    options.body=JSON.stringify(body||{});
  }
  const response=await fetch('/api/'+url,options);
  const json=await response.json().catch(()=>({error:'Máy chủ trả về dữ liệu không hợp lệ.'}));
  if(!response.ok) throw Error(json.error || 'Máy chủ trả về lỗi HTTP '+response.status);
  return json;
}
const optionsHtml = (values,selected) => values.map(x=>`<option value="${escapeHtml(x)}" ${x===selected?'selected':''}>${escapeHtml(x)}</option>`).join('');
function renderBookings() {
  if (!model.bookings.length) return '<div class="empty">Bạn chưa có lượt đặt sân nào.</div>';
  const labels={booked:'Đã ghi nhận',using:'Đang chơi',completed:'Đã trả sân',cancelled:'Đã hủy'};
  return `<div class="tablewrap"><table class="booktable"><thead><tr><th>Mã đặt</th><th>Sân</th><th>Ngày</th><th>Giờ</th><th>Trạng thái</th><th>Tiền sân</th><th>Đã thu</th></tr></thead><tbody>${model.bookings.map(x=>`<tr>
    <td>#${escapeHtml(x.id)}</td><td><strong>${escapeHtml(x.fieldName)}</strong></td><td>${escapeHtml(x.date)}</td><td>${escapeHtml(x.start)}–${escapeHtml(x.end)}</td><td><span class="pill ${escapeHtml(x.status)}">${escapeHtml(labels[x.status]||x.status)}</span></td><td>${fmtMoney(x.total)}</td><td>${fmtMoney(x.collected)}</td>
  </tr>`).join('')}</tbody></table></div>`;
}
function renderFind() {
  const field=model.fields.find(x=>String(x.id)===String(model.selectedField));
  if(!field) return '<div class="panel">Chưa có sân đang hoạt động.</div>';
  const now=new Date();
  const hour=now.getHours()*60+now.getMinutes();
  const initialStart=timeOptions.find(t=>model.day!==todayString() || toMinutes(t)>hour) || '17:00';
  const later=timeOptions.filter(t=>toMinutes(t)>toMinutes(initialStart));
  const initialEnd=later.find(t=>toMinutes(t)>=toMinutes(initialStart)+90)||later[0]||'18:30';
  return `<div class="two"><section class="panel">
    <div class="sectiontitle"><h2>Chọn sân &amp; thời gian</h2><span class="pill">Bước 1 / 2</span></div>
    <div class="field-grid">${model.fields.map(x=>`<button type="button" class="pitch" data-field="${x.id}" style="text-align:left;${x.id===model.selectedField?'border-color:#19965c;box-shadow:0 0 0 2px #d4f2dd;':''}">
      <div class="type">Sân ${escapeHtml(x.type)} người</div><h3>${escapeHtml(x.name)}</h3><div class="price">${fmtMoney(x.hourlyRate)}<span style="font-size:11px;font-weight:400"> /giờ</span></div><span class="pill">${x.id===model.selectedField?'Đang chọn':'Chọn sân'}</span>
    </button>`).join('')}</div>
    <form id="bookForm"><div class="grid2"><div class="field"><label for="bookingDate">Ngày đá</label><input id="bookingDate" type="date" name="date" min="${todayString()}" value="${escapeHtml(model.day)}" required></div>
    <div class="field"><label for="bookingField">Sân đã chọn</label><input id="bookingField" type="text" value="${escapeHtml(field.name)}" readonly></div></div>
    <div class="grid2"><div class="field"><label for="bookingStart">Giờ bắt đầu</label><select id="bookingStart" name="start" required>${optionsHtml(timeOptions.slice(0,-1),initialStart)}</select></div>
    <div class="field"><label for="bookingEnd">Giờ kết thúc</label><select id="bookingEnd" name="end" required>${optionsHtml(timeOptions.slice(1),initialEnd)}</select></div></div>
    <p class="helper">Thời gian từ 06:00–23:00, mỗi lượt 30–180 phút. Đặt tối đa 3 lịch đang chờ/sử dụng trong bản demo.</p>
    <button class="btn full" type="submit">Kiểm tra và xác nhận đặt sân</button></form>
    <div class="warn" style="margin-top:15px">⚠️ <b>Chưa thanh toán trực tuyến.</b> Lịch đặt được lưu để nhân viên theo dõi. Phần yêu cầu đặt cọc và thanh toán sẽ bổ sung ở Giai đoạn 3.</div>
  </section><aside class="panel">
    <h2>Khung giờ đã có lịch</h2><p class="muted">Ngày <b>${escapeHtml(model.day)}</b> · <b>${escapeHtml(field.name)}</b></p>
    <div class="slots" id="busySlots">${model.busy.length?model.busy.map(x=>`<span class="slot busy">${escapeHtml(x.start)}–${escapeHtml(x.end)}</span>`).join(''):'<span class="slot">Chưa có lịch trong ngày này</span>'}</div>
    <p class="muted">Chỉ hiển thị thời gian đã đặt, không hiển thị danh tính khách hàng khác.</p>
    <button class="btn soft full" type="button" data-reload="availability">Cập nhật lịch sân</button>
  </aside></div>`;
}
function render() {
  if(!model.session?.authenticated){window.location.replace('/');return;}
  $('#who').textContent= model.customer?.name || model.session.username;
  $('#logout').hidden=false;$('#tabFind').hidden=false;$('#tabMine').hidden=false;
  $('#tabFind').classList.toggle('selected',model.view==='find');
  $('#tabMine').classList.toggle('selected',model.view==='mine');
  $('#app').innerHTML=model.view==='find' ? renderFind() : `<section class="panel"><div class="sectiontitle"><h2>Lịch đặt sân của tôi</h2><button class="btn soft" type="button" data-reload="bookings">Tải lại</button></div>${renderBookings()}</section>`;
}
async function loadAvailability() {
  if(!model.selectedField) return;
  const query=new URLSearchParams({date:model.day,fieldId:model.selectedField});
  const response=await request('customer/availability/?'+query.toString());
  model.busy=response.busy;
}
async function loadMine(){ const r=await request('customer/bookings/');model.bookings=r.items; }
async function loadPortal() {
  const r=await request('customer/fields/');
  model.fields=r.fields; model.customer=r.customer;model.day=r.today;
  if(!model.fields.find(x=>x.id===model.selectedField)) model.selectedField=model.fields[0]?.id ?? null;
  await Promise.all([loadAvailability(),loadMine()]);render();
}
async function initialize() {
  try {
    model.session=await request('session/');
    if(!model.session.authenticated || model.session.role!=='Customer') {window.location.replace('/');return;}
    await loadPortal();
  } catch(err){ $('#app').innerHTML='<section class="panel">Không kết nối được máy chủ Django. Vui lòng kiểm tra Terminal.</section>';notification(err.message,true); }
}
async function submitForm(form) {
  const d=Object.fromEntries(new FormData(form).entries());
  if(form.id==='bookForm') {
    const start=d.start,end=d.end;
    const minutes=toMinutes(end)-toMinutes(start);
    if(minutes<30 || minutes>180) throw Error('Vui lòng chọn thời lượng từ 30 đến 180 phút.');
    const field=model.fields.find(x=>String(x.id)===String(model.selectedField));
    const estimate=Math.round(field.hourlyRate*minutes/60);
    const query=new URLSearchParams({date:d.date,fieldId:field.id,start,end});
    const available=await request('customer/availability/?'+query.toString());
    if(!available.available) { await loadAvailability();render();throw Error('Khung giờ đã có người đặt. Hãy chọn giờ khác.'); }
    if(!confirm(`Đặt ${field.name} ngày ${d.date}, ${start}–${end}?\nTiền sân dự kiến: ${fmtMoney(estimate)}.\nChưa thu tiền cọc ở giai đoạn này.`))return;
    const result=await request('customer/bookings/','POST',{fieldId:field.id,date:d.date,start,end});
    await loadAvailability();await loadMine();model.view='mine';render();
    notification(`Đã lưu lịch đặt #${result.booking.id}. Chưa thanh toán cọc. Nhân viên sẽ xác nhận ở bước tiếp theo.`);return;
  }
}
document.addEventListener('click',async e=>{
  const view=e.target.closest('[data-view]');const field=e.target.closest('[data-field]');const reload=e.target.closest('[data-reload]');
  try{
    if(view){model.view=view.dataset.view;if(model.view==='mine') await loadMine();render();clearNotification();}
    if(field){model.selectedField=Number(field.dataset.field);await loadAvailability();render();}
    if(reload){if(reload.dataset.reload==='bookings')await loadMine();else await loadAvailability();render();notification('Đã cập nhật dữ liệu.');}
  }catch(err){notification(err.message,true);}
});
document.addEventListener('change',async e=>{
  if(e.target.id==='bookingDate'){
    model.day=e.target.value;try{await loadAvailability();render();}catch(err){notification(err.message,true);}
  }
});
document.addEventListener('submit',async e=>{
  if(e.target.id!=='bookForm')return;
  e.preventDefault();const button=e.target.querySelector('[type=submit]');if(button)button.disabled=true;
  try{await submitForm(e.target);}catch(err){notification(err.message,true);}finally{if(button)button.disabled=false;}
});
$('#logout').addEventListener('click',async()=>{
  try{await request('session/','DELETE');window.location.replace('/');}
  catch(err){notification(err.message,true);}
});
initialize();
