/* PitchPro - mot trang dang nhap va dang ky, routing theo role o backend. */
'use strict';

const $ = selector => document.querySelector(selector);
const destination = Object.freeze({
  Customer: '/khach/',
  Staff: '/nhan-vien/',
  Manager: '/quan-ly/'
});
let busy = false;
let currentMode = 'login';

function csrf() {
  const match = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : '';
}

function feedback(message = '', success = false) {
  const el = $('#feedback');
  el.textContent = message;
  el.className = 'feedback' + (success ? ' success' : '');
  el.hidden = !message;
}

function setBusy(value, button) {
  busy = value;
  const controls = document.querySelectorAll('.auth-switch button, .submit-button');
  controls.forEach(control => {control.disabled = value;});
  if (button) {
    const text = button.querySelector('span');
    text.textContent = value ? 'Đang xử lý...' : button.dataset.defaultLabel;
  }
}

function chooseMode(mode, updateHistory = true) {
  if (busy) return;
  currentMode = mode === 'register' ? 'register' : 'login';
  const isRegister = currentMode === 'register';
  $('#login-form').hidden = isRegister;
  $('#register-form').hidden = !isRegister;
  $('#login-tab').classList.toggle('active', !isRegister);
  $('#register-tab').classList.toggle('active', isRegister);
  $('#login-tab').setAttribute('aria-selected', String(!isRegister));
  $('#register-tab').setAttribute('aria-selected', String(isRegister));
  $('#auth-title').textContent = isRegister ? 'Tạo tài khoản khách hàng' : 'Đăng nhập tài khoản';
  $('#auth-description').textContent = isRegister
    ? 'Đăng ký một lần để tự chọn sân, đặt lịch và theo dõi các lượt đặt của bạn.'
    : 'Sử dụng tài khoản của bạn để truy cập đúng khu vực được phân quyền.';
  feedback();
  if (updateHistory) {
    const path = isRegister ? '/dang-ky/' : '/dang-nhap/';
    if (location.pathname !== path) history.pushState({mode: currentMode}, '', path);
  }
  document.title = (isRegister ? 'Đăng ký' : 'Đăng nhập') + ' | PitchPro';
}

async function send(path, payload) {
  const response = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    cache: 'no-store',
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      'X-CSRFToken': csrf()
    },
    body: JSON.stringify(payload)
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `Máy chủ phản hồi HTTP ${response.status}.`);
  }
  return data;
}

function routeByRole(role) {
  const path = destination[role];
  if (!path) throw new Error('Tài khoản chưa được phân quyền hợp lệ. Vui lòng liên hệ quản trị.');
  window.location.replace(path);
}

document.querySelectorAll('[data-mode]').forEach(tab => {
  tab.addEventListener('click', () => chooseMode(tab.dataset.mode));
});
document.querySelector('[data-open-register]').addEventListener('click', event => {
  event.preventDefault(); chooseMode('register');
});
document.querySelector('[data-open-login]').addEventListener('click', event => {
  event.preventDefault(); chooseMode('login');
});
window.addEventListener('popstate', () => chooseMode(
  location.pathname === '/dang-ky/' ? 'register' : 'login', false
));

document.querySelectorAll('[data-toggle-password]').forEach(btn => {
  btn.addEventListener('click', () => {
    const input = document.getElementById(btn.dataset.togglePassword);
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    btn.textContent = show ? 'Ẩn' : 'Hiện';
    btn.setAttribute('aria-label', show ? 'Ẩn mật khẩu' : 'Hiển thị mật khẩu');
  });
});

$('#login-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;
  const button = $('#login-submit');
  const form = event.currentTarget;
  const username = form.elements.username.value.trim();
  const password = form.elements.password.value;
  if (!username || !password) {feedback('Vui lòng nhập tên đăng nhập và mật khẩu.');return;}
  feedback();setBusy(true, button);
  try {
    const result = await send('/api/session/', {username, password});
    routeByRole(result.role);
  } catch (error) {
    feedback(error.message);
    setBusy(false, button);
  }
});

$('#register-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;
  const button = $('#register-submit');
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form).entries());
  if (values.password !== values.confirmPassword) {
    feedback('Hai mật khẩu chưa trùng khớp.');
    form.elements.confirmPassword.focus();
    return;
  }
  const {confirmPassword, ...payload} = values;
  feedback();setBusy(true, button);
  try {
    const result = await send('/api/customer/register/', payload);
    routeByRole(result.role);
  } catch (error) {
    feedback(error.message);
    setBusy(false, button);
  }
});

$('#login-submit').dataset.defaultLabel = 'Đăng nhập';
$('#register-submit').dataset.defaultLabel = 'Tạo tài khoản khách hàng';
chooseMode(location.pathname === '/dang-ky/' ? 'register' : 'login', false);
