/* PitchPro - QT02 frontend module. Tách khỏi app.js của Quy trình 1. */
(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const money2 = value => Number(value || 0).toLocaleString('vi-VN') + ' ₫';

  // Chỉ phục vụ biểu mẫu sao kê mô phỏng của Quy trình 2; không thay đổi API/DB.
  let bankDemoRows = [];
  function bankLocalDateTime(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    const two = n => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${two(date.getMonth() + 1)}-${two(date.getDate())}T${two(date.getHours())}:${two(date.getMinutes())}`;
  }
  function bankEntryRow(item = {}) {
    return `<div class="qt02-bank-entry" data-qt02-bank-row>
      <div class="qt02-bank-fields">
        <div class="field"><label>Mã giao dịch <span aria-hidden="true">*</span></label>
          <input name="reference" type="text" maxlength="120" autocomplete="off" placeholder="VD: CK-20261102-001" value="${esc2(item.reference || '')}"></div>
        <div class="field"><label>Số tiền (VNĐ) <span aria-hidden="true">*</span></label>
          <input name="amount" type="number" step="1" placeholder="VD: 300000" value="${esc2(item.amount ?? '')}"></div>
        <div class="field"><label>Diễn giải (không bắt buộc)</label>
          <input name="description" type="text" maxlength="250" placeholder="VD: Thanh toán HD-29" value="${esc2(item.description || '')}"></div>
        <div class="field"><label>Ngày giờ giao dịch (không bắt buộc)</label>
          <input name="transactionAt" type="datetime-local" value="${esc2(bankLocalDateTime(item.transactionAt))}"></div>
      </div>
      <button type="button" class="btn outline small qt02-bank-remove" data-qt02-action="bank-remove-row" aria-label="Xóa giao dịch sao kê này">Xóa dòng</button>
    </div>`;
  }
  function updateBankPreview(form) {
    const output = form?.querySelector('[data-qt02-bank-preview]');
    if (!output) return;
    const entries = [...form.querySelectorAll('[data-qt02-bank-row]')];
    const hasData = row => [...row.querySelectorAll('input')].some(input => String(input.value || '').trim());
    const filled = entries.filter(hasData);
    const amounts = filled.map(row => Number(row.querySelector('[name="amount"]').value));
    const valid = amounts.every(n => Number.isSafeInteger(n) && n !== 0);
    output.textContent = `${filled.length} giao dịch đang nhập` +
      (valid ? ` · Tổng tạm tính: ${money2(amounts.reduce((a, b) => a + b, 0))}` : ' · Kiểm tra số tiền còn thiếu/sai');
  }

  const esc2 = value => String(value ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
  const statusLabel = {
    draft: 'Đang đối soát',
    submitted: 'Chờ quản lý duyệt',
    approved: 'Đã duyệt',
    locked: 'Đã khóa sổ',
    open: 'Chờ giải trình',
    review_pending: 'Chờ quản lý duyệt phương án',
    rejected: 'Yêu cầu bổ sung',
    resolved: 'Đã xử lý và khớp',
    approved_exception: 'Quản lý chấp nhận phương án'
  };
  const statusClass = value => {
    if (['locked', 'resolved'].includes(value)) return 'success';
    if (['approved', 'submitted', 'review_pending'].includes(value)) return 'info';
    if (['open', 'rejected', 'draft'].includes(value)) return 'warning';
    return 'muted';
  };
  const pill = (value, label) =>
    `<span class="qt02-pill ${statusClass(value)}">${esc2(label || statusLabel[value] || value)}</span>`;

  function page() {
    return heading(
      'Đối soát doanh thu cuối ngày',
      'Tổng hợp các khoản thu và kiểm tra chênh lệch cuối ngày.'
    ) + `
      <div class="toolbar qt02-toolbar">
        <label>Ngày nghiệp vụ
          <input class="dateinput" type="date" id="dateRecon" value="${esc2(selectedDay)}" max="${DB?.today || ''}">
        </label>
        <button class="btn outline" type="button" data-qt02-action="reload">Tải số liệu</button>
      </div>
      <div id="qt02Panel"><div class="panel"><p class="muted">Đang tải dữ liệu đối soát...</p></div></div>`;
  }

  function statCard(label, value, note = '') {
    return `<div class="stat"><label>${esc2(label)}</label><b>${esc2(value)}</b><small>${esc2(note)}</small></div>`;
  }

  function panel(title, body, extra = '') {
    return `<section class="panel qt02-panel"><div class="qt02-panel-head"><h2>${title}</h2>${extra}</div>${body}</section>`;
  }

  function actionButton(label, action, id = '', cls = 'outline') {
    return `<button type="button" class="btn ${cls}" data-qt02-action="${esc2(action)}" data-id="${esc2(id)}">${label}</button>`;
  }

  function aiResultPanel(analysis, scope = '', allowFill = false) {
    if (!analysis?.result) return '';
    const result = analysis.result;
    const list = values => (values || []).length
      ? `<ul>${values.map(value => `<li>${esc2(value)}</li>`).join('')}</ul>`
      : '<p class="muted">Chưa có dữ kiện cụ thể.</p>';
    return `<div class="qt02-ai-result">
      <div class="qt02-ai-result-head"><b>✦ GỢI Ý TỪ AI</b><small>${esc2(analysis.model || 'AI')} · ${esc2(analysis.createdAt ? new Date(analysis.createdAt).toLocaleString('vi-VN') : '')}</small></div>
      <p><b>Tóm tắt:</b> ${esc2(result.summary || 'Chưa đủ dữ liệu để tóm tắt.')}</p>
      <div class="qt02-ai-columns">
        <div><b>Nguyên nhân có thể</b>${list(result.possible_causes)}</div>
        <div><b>Dữ kiện AI đã nhận diện</b>${list(result.supporting_evidence)}</div>
        <div><b>Nhân viên cần kiểm tra</b>${list(result.checks_to_perform)}</div>
        <div><b>Điểm còn chưa chắc chắn</b>${list(result.uncertainties)}</div>
      </div>
      ${result.suggested_reason ? `<p><b>Nguyên nhân tham khảo:</b> ${esc2(result.suggested_reason)}</p>` : ''}
      ${result.suggested_action ? `<p><b>Hướng xử lý tham khảo:</b> ${esc2(result.suggested_action)}</p>` : ''}
      ${allowFill ? `<div class="actions">
        <button type="button" class="btn outline small" data-qt02-action="ai-use-reason" data-id="${esc2(scope)}" data-text="${esc2(result.suggested_reason || '')}">Dùng gợi ý nguyên nhân</button>
        <button type="button" class="btn outline small" data-qt02-action="ai-use-action" data-id="${esc2(scope)}" data-text="${esc2(result.suggested_action || '')}">Dùng gợi ý phương án</button>
      </div>` : ''}
      <p class="qt02-ai-disclaimer">Gợi ý chỉ để tham khảo; nhân viên cần kiểm tra trước khi xác nhận.</p>
    </div>`;
  }

  function aiStatusNotice(ai) {
    if (ai?.available) return '';
    return '<div class="qt02-ai-status unavailable">Chức năng gợi ý bằng AI chưa sẵn sàng. Vui lòng liên hệ quản trị viên.</div>';
  }

  function csrfToken2() {
    return decodeURIComponent((document.cookie.match(/(?:^|; )csrftoken=([^;]*)/) || [])[1] || '');
  }

  async function uploadExceptionEvidence(day, exceptionId, file) {
    const formData = new FormData();
    formData.append('file', file);
    const response = await fetch(
      `/api/reconciliation/${encodeURIComponent(day)}/exceptions/${encodeURIComponent(exceptionId)}/evidence/`,
      {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Accept': 'application/json', 'X-CSRFToken': csrfToken2()},
        body: formData
      }
    );
    let payload;
    try { payload = await response.json(); }
    catch { throw new Error(`Server trả về lỗi HTTP ${response.status}`); }
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    return payload;
  }

  function pendingPanel(d) {
    if (!d.pendingInvoices?.length) {
      return panel('Khoản treo tại thời điểm chốt', '<p class="qt02-ok">Không có hóa đơn còn phải thu tại thời điểm chốt ngày.</p>');
    }
    return panel(
      'Khoản treo tại thời điểm chốt',
      `<p class="muted"><b>Khoản treo</b> là tiền hóa đơn chưa thu đủ khi chốt ngày. Chọn <b>Chuyển kỳ sau</b> để tiếp tục theo dõi, hoặc <b>Đã tất toán sau ngày chốt</b> khi có chứng từ thu đủ tiền.</p>
       <div class="tablebox"><table><thead><tr><th>Hóa đơn</th><th>Khách hàng</th><th>Còn phải thu tại mốc chốt</th><th>Hiện tại</th><th>Phương án</th></tr></thead>
       <tbody>${d.pendingInvoices.map(item => {
         const resolution = item.resolution;
         const staleResolution = resolution && (d.unresolvedPendingIds || []).includes(item.invoiceId);
         const editable = d.status === 'draft' && !DB.user.manager;
         return `<tr>
           <td><b>HD-${item.invoiceId}</b></td>
           <td>${esc2(item.customer)}</td>
           <td>${money2(item.amountDue)}</td>
           <td>${money2(item.currentDue)}</td>
           <td>
             ${editable ? `${staleResolution ? '<b class="qt02-alert">Số dư thay đổi – cần cập nhật phương án</b>' : ''}
                  <form class="qt02-inline-form" data-qt02-form="pending">
                    <input type="hidden" name="invoiceId" value="${item.invoiceId}">
                    <select name="disposition">
                      <option value="carry_forward" ${resolution?.disposition === 'carry_forward' ? 'selected' : ''}>Chuyển kỳ sau</option>
                      <option value="settled_later" ${resolution?.disposition === 'settled_later' ? 'selected' : ''}>Đã tất toán sau ngày chốt</option>
                    </select>
                    <input name="note" value="${esc2(resolution?.note || '')}" placeholder="Ghi căn cứ / mã chứng từ" minlength="10" required>
                    <button class="btn small" type="submit">${resolution ? 'Cập nhật' : 'Lưu'}</button>
                  </form>`
               : resolution && !staleResolution
                 ? `<b class="qt02-ok">${resolution.disposition === 'settled_later' ? 'Đã tất toán sau ngày chốt' : 'Chuyển kỳ sau'}</b><small>${esc2(resolution.note)}</small>`
                 : `<span class="muted">${staleResolution ? 'Số dư đã thay đổi – nhân viên cần cập nhật phương án.' : 'Chưa có phương án – chỉ nhân viên được xử lý khi kỳ đang mở.'}</span>`}
           </td>
         </tr>`;
       }).join('')}</tbody></table></div>`
    );
  }

  function cashPanel(d) {
    const s = d.session || d;
    const isDraft = s.status === 'draft' && !DB.user.manager;
    const expected = s.cashExpected;
    const diff = s.cashDifference;
    const calc = expected == null ? 'Chưa đủ dữ liệu' : money2(expected);
    const diffLabel = diff == null ? 'Chưa kiểm đếm' : `${diff < 0 ? 'Thiếu ' : diff > 0 ? 'Thừa ' : 'Khớp '}${money2(Math.abs(diff))}`;
    return panel('1. Đối chiếu quỹ tiền mặt', `
      <div class="qt02-gridstats">
        ${statCard('Tiền mặt đã ghi nhận (ròng)', money2(s.ledgerCash), 'Đã trừ các khoản hoàn tiền')}
        ${statCard('Quỹ đầu ca', s.openingCash == null ? 'Chưa nhập' : money2(s.openingCash))}
        ${statCard('Tiền đã chi / chuyển khỏi quỹ', money2(s.cashTransferOut))}
        ${statCard('Số dư quỹ dự kiến', calc)}
        ${statCard('Tiền thực kiểm', s.countedCash == null ? 'Chưa nhập' : money2(s.countedCash))}
        ${statCard('Chênh lệch', diffLabel, 'Âm = thiếu · Dương = thừa')}
      </div>
      <p class="muted">Dòng tiền: cọc ${money2(s.cashByKind?.deposit || 0)} · thanh toán ${money2(s.cashByKind?.settlement || 0)} · hoàn tiền ${money2(s.cashByKind?.refund || 0)}.</p>
      ${isDraft ? `<form class="qt02-form" data-qt02-form="cash">
        <div class="formgrid">
          <div class="field"><label>Quỹ đầu ca (VNĐ)</label><input name="openingCash" type="number" min="0" step="1" required value="${s.openingCash ?? 0}"></div>
          <div class="field"><label>Tiền đã chi / chuyển khỏi quỹ (VNĐ)</label><input name="cashTransferOut" type="number" min="0" step="1" required value="${s.cashTransferOut ?? 0}"></div>
          <div class="field"><label>Tiền mặt thực kiểm (VNĐ)</label><input name="countedCash" type="number" min="0" step="1" required value="${s.countedCash ?? ''}"></div>
          <div class="field"><label>Biên bản kiểm đếm / căn cứ</label><input name="notes" required minlength="5" value="${esc2(s.notes || '')}" placeholder="Ví dụ: Biên bản kiểm quỹ cuối ca..."></div>
        </div>
        <button class="btn" type="submit">Lưu kiểm đếm quỹ</button>
      </form>` : `<p class="muted">Kỳ đã trình hoặc khóa; không thể sửa số kiểm đếm.</p>`}
    `);
  }

  function bankPanel(d) {
    const s = d.session || d;
    const bank = s.bank || {};
    const isDraft = s.status === 'draft' && !DB.user.manager;
    const difference = s.bankDifference;
    const diffLabel = difference == null ? 'Chưa nhập sao kê' : `${difference < 0 ? 'Thiếu ' : difference > 0 ? 'Thừa ' : 'Khớp '}${money2(Math.abs(difference))}`;
    const rows = bank.actual || [];
    // Chỉ dùng để minh họa test; sao kê thật phải nhập từ chứng từ ngân hàng độc lập.
    const sampleByRef = new Map();
    for (const item of bank.expected || []) {
      const reference = String(item.reference || '').trim();
      const amount = Number(item.amount);
      if (reference.length < 3 || !Number.isSafeInteger(amount) || amount === 0) continue;
      const key = reference.toUpperCase();
      if (sampleByRef.has(key)) {
        sampleByRef.get(key).amount += amount;
      } else {
        sampleByRef.set(key, {
          reference, amount,
          description: `Dữ liệu mẫu HD-${item.invoiceId}`,
          transactionAt: ''
        });
      }
    }
    bankDemoRows = [...sampleByRef.values()].filter(item => item.amount !== 0);

    return panel('2. Đối chiếu sao kê ngân hàng', `
      <div class="qt02-gridstats">
        ${statCard('Chuyển khoản đã ghi nhận', money2(s.ledgerBank), 'Đã trừ các khoản hoàn tiền')}
        ${statCard('Tổng trên sao kê', bank.imported ? money2(bank.actualTotal) : 'Chưa nhập')}
        ${statCard('Chênh lệch sao kê', diffLabel)}
        ${statCard('Khớp / thiếu / thừa / sai tiền',
          `${bank.matched?.length || 0} / ${bank.missing?.length || 0} / ${bank.extra?.length || 0} / ${bank.mismatched?.length || 0}`,
          'Đối chiếu theo mã giao dịch và số tiền')}
      </div>
      <p class="muted">Dòng tiền: cọc ${money2(s.bankByKind?.deposit || 0)} · thanh toán ${money2(s.bankByKind?.settlement || 0)} · hoàn tiền ${money2(s.bankByKind?.refund || 0)}.</p>
      ${bank.imported ? `<p class="muted">Nguồn: <b>${esc2(bank.source)}</b> · Nhập lúc ${esc2(new Date(bank.importedAt).toLocaleString('vi-VN'))}</p>` : '<p class="muted">Chưa có dữ liệu sao kê.</p>'}
      ${bank.expected?.length ? `<div class="qt02-help"><b>Giao dịch chuyển khoản đã ghi nhận</b><div class="tablebox"><table><thead><tr><th>Mã giao dịch</th><th>Hóa đơn</th><th>Số tiền</th><th>Thời điểm xác nhận</th></tr></thead><tbody>${bank.expected.map(x => `<tr><td><code>${esc2(x.reference || 'THIẾU MÃ')}</code><small>${esc2(x.requestCode || '')}</small></td><td>HD-${x.invoiceId}</td><td>${money2(x.amount)}</td><td>${esc2(x.confirmedAt ? new Date(x.confirmedAt).toLocaleString('vi-VN') : 'Chưa có')}</td></tr>`).join('')}</tbody></table></div></div>` : ''}
      ${isDraft ? `<form class="qt02-form" data-qt02-form="bank">
        <div class="formgrid">
          <div class="field"><label>Tên / nguồn sao kê</label><input name="source" required minlength="3" value="${esc2(bank.source || 'Sao kê ngân hàng')}"></div>
          <div class="field qt02-wide">
            <label>Giao dịch ngân hàng</label>
            <small>Nhập từng giao dịch trên sao kê ngân hàng. Khoản hoàn tiền ghi số âm.</small>
            <div data-qt02-bank-rows class="qt02-bank-entries">${rows.length ? rows.map(bankEntryRow).join('') : bankEntryRow()}</div>
            <div class="qt02-bank-tools">
              <button class="btn outline small" type="button" data-qt02-action="bank-add-row">+ Thêm giao dịch</button>
              ${bankDemoRows.length ? '<button class="btn outline small" type="button" data-qt02-action="bank-demo-fill">Điền sao kê mẫu</button>' : ''}
            </div>
            <small>Sao kê mẫu chỉ dùng để kiểm thử, không thay thế chứng từ ngân hàng.</small>
            <output class="qt02-bank-preview" data-qt02-bank-preview>${rows.length} giao dịch đang nhập · Tổng tạm tính: ${money2(rows.reduce((total, item) => total + Number(item.amount || 0), 0))}</output>
          </div>
        </div>
        <button class="btn" type="submit">Lưu / cập nhật sao kê</button>
      </form>` : ''}
      ${bank.matched?.length ? `<div class="tablebox"><table><thead><tr><th>Mã giao dịch đã khớp</th><th>Hóa đơn</th><th>Thời điểm xác nhận thu</th><th>Thời điểm sao kê</th><th>Lệch phút</th></tr></thead><tbody>${bank.matched.map(x => `<tr><td><code>${esc2(x.reference)}</code></td><td>HD-${x.invoiceId}</td><td>${esc2(x.paymentConfirmedAt ? new Date(x.paymentConfirmedAt).toLocaleString('vi-VN') : '—')}</td><td>${esc2(x.statementTransactionAt ? new Date(x.statementTransactionAt).toLocaleString('vi-VN') : '—')}</td><td>${x.timeDeltaMinutes == null ? '—' : x.timeDeltaMinutes}</td></tr>`).join('')}</tbody></table></div>` : ''}
      ${rows.length ? `<div class="tablebox"><table><thead><tr><th>Mã giao dịch trên sao kê</th><th>Số tiền</th><th>Diễn giải</th><th>Thời điểm</th></tr></thead><tbody>${rows.map(x => `<tr><td><code>${esc2(x.reference)}</code></td><td>${money2(x.amount)}</td><td>${esc2(x.description)}</td><td>${esc2(x.transactionAt ? new Date(x.transactionAt).toLocaleString('vi-VN') : 'Không cung cấp')}</td></tr>`).join('')}</tbody></table></div>` : ''}
      ${bank.missing?.length || bank.missingReference?.length || bank.extra?.length || bank.mismatched?.length || bank.dateMismatch?.length ? `<div class="qt02-alert">
        <b>Các giao dịch cần kiểm tra:</b>
        ${bank.missingReference?.map(x => `<p>Thiếu mã giao dịch ngân hàng: Giao dịch #${x.paymentId} · ${money2(x.amount)}</p>`).join('') || ''}
        ${bank.missing?.map(x => `<p>Thiếu trên sao kê: ${esc2(x.reference)} · ${money2(x.amount)}</p>`).join('') || ''}
        ${bank.extra?.map(x => `<p>Thừa trên sao kê: ${esc2(x.reference)} · ${money2(x.amount)}</p>`).join('') || ''}
        ${bank.mismatched?.map(x => `<p>Sai số tiền: ${esc2(x.reference)} · Sổ ${money2(x.expected)} / Sao kê ${money2(x.actual)}</p>`).join('') || ''}
        ${bank.dateMismatch?.map(x => `<p>Sai ngày giao dịch: ${esc2(x.reference)} · Sao kê ${esc2(x.actualDay)} / Kỳ ${esc2(x.expectedDay)}</p>`).join('') || ''}
      </div>` : ''}
    `);
  }

  function exceptionPanel(d) {
    const cases = d.exceptions || [];
    return panel('3. Yêu cầu ngoại lệ và phê duyệt', cases.length ? cases.map(item => `
      <article class="qt02-exception" data-qt02-exception="${item.id}">
        <div class="qt02-exception-head">
          <div><b>${esc2(item.code)}</b><p>${esc2(item.description)}</p></div>
          ${pill(item.status, item.statusLabel)}
        </div>
        ${item.reason ? `<p><b>Nguyên nhân:</b> ${esc2(item.reason)}</p>` : ''}
        ${item.evidence ? `<p><b>Chứng từ / bằng chứng:</b> ${esc2(item.evidence)}</p>` : ''}
        ${item.proposedAction ? `<p><b>Phương án:</b> ${esc2(item.proposedAction)}</p>` : ''}
        ${item.managerFeedback ? `<p><b>Ý kiến quản lý:</b> ${esc2(item.managerFeedback)}</p>` : ''}
        ${item.evidenceDocuments?.length ? `<div class="qt02-evidence-list"><b>Chứng từ đã tải:</b>${item.evidenceDocuments.map(file => `<div>📎 ${esc2(file.originalName)} <small>· ${esc2(file.uploadedBy)} · ${esc2(new Date(file.uploadedAt).toLocaleString('vi-VN'))}</small></div>`).join('')}</div>` : ''}
        ${d.status === 'draft' && ['open','rejected'].includes(item.status) && !DB.user.manager ? `
          <form class="qt02-ai-form" data-qt02-form="ai-exception">
            <input type="hidden" name="exceptionId" value="${item.id}">
            <div class="field"><label>Nội dung chứng từ để AI đọc (có thể dán thêm diễn giải, biên bản, nội dung sao kê)</label>
              <textarea name="evidenceText" rows="3" placeholder="Dán phần nội dung quan trọng của chứng từ nếu không tải tệp..."></textarea>
            </div>
            <div class="field"><label>Tải chứng từ (PDF có văn bản, TXT hoặc CSV; tối đa 5 MB)</label>
              <input type="file" name="evidenceFile" accept=".pdf,.txt,.csv,application/pdf,text/plain,text/csv">
              <small>PDF dạng ảnh chưa hỗ trợ đọc tự động. Nội dung gửi tới dịch vụ AI khi phân tích; vui lòng che thông tin nhạy cảm.</small>
            </div>
            <button class="btn small qt02-ai-button" type="submit" ${d.ai?.available ? '' : 'disabled title="Chưa cấu hình nhà cung cấp AI"'}>✦ AI đọc chứng từ và gợi ý nguyên nhân</button>
          </form>` : ''}
        ${aiResultPanel(item.aiAnalysis, item.id, d.status === 'draft' && ['open','rejected'].includes(item.status) && !DB.user.manager)}
        ${d.status === 'draft' && ['open','rejected'].includes(item.status) && !DB.user.manager ? `
          <form class="qt02-form" data-qt02-form="explain">
            <input type="hidden" name="exceptionId" value="${item.id}">
            <div class="formgrid">
              <div class="field"><label>Nguyên nhân do nhân viên xác nhận</label><textarea name="reason" required minlength="8">${esc2(item.reason || '')}</textarea></div>
              <div class="field"><label>Chứng từ / bằng chứng đã kiểm tra</label><textarea name="evidence" required minlength="5">${esc2(item.evidence || '')}</textarea></div>
              <div class="field qt02-wide"><label>Phương án xử lý do nhân viên đề xuất</label><textarea name="proposedAction" required minlength="8">${esc2(item.proposedAction || '')}</textarea></div>
            </div>
            <button class="btn small" type="submit">Gửi giải trình cho Quản lý</button>
          </form>` : ''}
        ${d.status === 'draft' && item.status === 'review_pending' && DB.user.manager ? `
          <div class="actions">
            ${actionButton('Chấp nhận phương án', 'exception-approve', item.id, 'soft')}
            ${actionButton('Yêu cầu bổ sung', 'exception-reject', item.id, 'outline')}
          </div>` : ''}
        ${item.history?.length ? `<details class="qt02-history"><summary>Lịch sử giải trình và quyết định (${item.history.length})</summary>${item.history.map(row => `
          <div class="qt02-history-item"><b>Lần ${row.revisionNo}: ${esc2(row.action)}</b>
            <p>${esc2(row.reason)}</p><p><b>Chứng từ:</b> ${esc2(row.evidence)}</p>
            <p><b>Phương án:</b> ${esc2(row.proposedAction)}</p>
            ${row.managerFeedback ? `<p><b>Ý kiến quản lý:</b> ${esc2(row.managerFeedback)}</p>` : ''}
            <small>${esc2(row.actor)} · ${esc2(new Date(row.createdAt).toLocaleString('vi-VN'))}</small>
          </div>`).join('')}</details>` : ''}
        ${item.status === 'approved' ? '<p class="qt02-ok">Quản lý đã chấp nhận phương án xử lý.</p>' : ''}
        ${item.status === 'resolved' ? `<p class="qt02-ok">Đã khớp lại. ${esc2(item.resolution || '')}</p>` : ''}
      </article>
    `).join('') : '<p class="qt02-ok">Chưa có hồ sơ chênh lệch. Nhấn “Kiểm tra và phát hiện ngoại lệ” sau khi hoàn tất nhập liệu.</p>') +
    (d.status === 'draft' && !DB.user.manager ? `<div class="actions">${actionButton('Kiểm tra và phát hiện ngoại lệ', 'detect', '', 'outline')}</div>` : '');
  }

  function actionsPanel(d) {
    const manager = !!DB.user.manager;
    let controls = '';
    if (d.status === 'draft' && !manager) {
      controls = actionButton('Nhân viên trình báo cáo', 'submit', '', 'primary');
    } else if (d.status === 'draft' && manager) {
      controls = '<p class="muted">Đang chờ Nhân viên hoàn tất đối soát và trình báo cáo.</p>';
    } else if (d.status === 'submitted' && manager) {
      controls = actionButton('Quản lý duyệt báo cáo', 'approve', '', 'primary') +
        actionButton('Trả lại để bổ sung', 'return', '', 'outline');
    } else if (d.status === 'approved' && manager) {
      controls = actionButton('Khóa sổ và lưu snapshot', 'lock', '', 'primary') +
        actionButton('Trả lại để bổ sung', 'return', '', 'outline');
    } else if (d.status === 'locked') {
      controls = actionButton('Tải báo cáo CSV', 'report', '', 'outline');
    } else if (d.status === 'submitted') {
      controls = '<p class="muted">Đang chờ Quản lý xem xét và phê duyệt.</p>';
    } else if (d.status === 'approved') {
      controls = '<p class="muted">Báo cáo đã được duyệt, chờ Quản lý khóa sổ.</p>';
    }
    return panel('4. Trình duyệt và khóa sổ', `
      <p class="muted">Trạng thái: ${pill(d.status)}</p>
      ${d.submittedAt ? `<p>Nhân viên trình lúc: ${esc2(new Date(d.submittedAt).toLocaleString('vi-VN'))}</p>` : ''}
      ${d.approvedAt ? `<p>Quản lý duyệt lúc: ${esc2(new Date(d.approvedAt).toLocaleString('vi-VN'))}</p>` : ''}
      ${d.lockedAt ? `<p>Khóa sổ lúc: ${esc2(new Date(d.lockedAt).toLocaleString('vi-VN'))}</p>` : ''}
      <div class="actions">${controls}</div>
    `);
  }

  function reminderPanel(items) {
    const unread = (items || []).filter(item => !item.readAt);
    if (!unread.length) return '';
    return panel('Thông báo cần xác nhận', unread.map(item => `
      <div class="qt02-exception">
        <div class="qt02-exception-head">
          <div><b>Đối soát ngày ${esc2(item.day)}</b><p>${esc2(item.message)}</p>
            <small>Đến hạn lúc ${esc2(new Date(item.dueAt).toLocaleString('vi-VN'))}</small>
          </div>
          ${actionButton('Đã xem', 'reminder-read', item.id, 'outline')}
        </div>
      </div>
    `).join(''));
  }

  async function fill() {
    const target = $('#qt02Panel');
    if (!target) return;
    const [d, reminderData] = await Promise.all([
      api('reconciliation/?date=' + encodeURIComponent(selectedDay)),
      DB.user.manager ? api('reconciliation/reminders/') : Promise.resolve({items: []})
    ]);
    const reminders = DB.user.manager ? reminderPanel(reminderData.items || []) : '';
    if (!d.session) {
      target.innerHTML = reminders + `
        <div class="gridstats">
          ${statCard('Tiền mặt đã ghi nhận', money2(d.ledgerCash))}
          ${statCard('Chuyển khoản đã ghi nhận', money2(d.ledgerBank))}
        </div>
        <section class="panel qt02-panel">
          <h2>Chưa mở kỳ đối soát ${esc2(selectedDay)}</h2>
          <p class="muted">Số liệu được tổng hợp từ các giao dịch đã xác nhận. Mở kỳ để kiểm đếm quỹ, nhập sao kê và xử lý các khoản chưa thu.</p>
          ${d.canOpen && !DB.user.manager ? actionButton('Mở kỳ đối soát', 'open', '', 'primary') : '<p class="muted">Không thể mở kỳ: cần đúng ngày nghiệp vụ và vai trò Nhân viên.</p>'}
        </section>`;
      return;
    }

    const s = d.session;
    target.innerHTML = reminders + aiStatusNotice(s.ai) + `
      <div class="qt02-topline">${pill(s.status)} <span>Ngày nghiệp vụ: <b>${esc2(s.day)}</b></span></div>
      <div class="gridstats">
        ${statCard('Tiền mặt đã ghi nhận (ròng)', money2(s.ledgerCash), 'Đã trừ các khoản hoàn tiền')}
        ${statCard('Chuyển khoản đã ghi nhận', money2(s.ledgerBank), 'Đã trừ các khoản hoàn tiền')}
        ${statCard('Tiền mặt chênh lệch', s.cashDifference == null ? 'Chưa kiểm' : money2(s.cashDifference), 'Âm = thiếu · Dương = thừa')}
        ${statCard('Chênh lệch sao kê', s.bankDifference == null ? 'Chưa nhập' : money2(s.bankDifference))}
      </div>
      ${cashPanel(s)}
      ${bankPanel(s)}
      ${pendingPanel(s)}
      ${exceptionPanel(s)}
      ${actionsPanel(s)}
      ${s.status === 'locked' && s.reportSnapshot ? `<section class="panel"><h2>Báo cáo đã khóa</h2><p>Số liệu và chứng từ đã được lưu tại thời điểm khóa sổ.</p></section>` : ''}
    `;
  }

  async function postAndRefresh(path, body, message) {
    await api(path, 'POST', body);
    await refresh();
    await fill();
    if (message) toast(message);
  }

  async function clickAction(action, id, target) {
    const day = selectedDay;
    if (action === 'reload') return fill();
    if (action === 'bank-add-row') {
      const form = target.closest('form[data-qt02-form="bank"]');
      const holder = form?.querySelector('[data-qt02-bank-rows]');
      if (!holder) return;
      holder.insertAdjacentHTML('beforeend', bankEntryRow());
      holder.lastElementChild.querySelector('[name="reference"]')?.focus();
      updateBankPreview(form);
      return;
    }
    if (action === 'bank-remove-row') {
      const form = target.closest('form[data-qt02-form="bank"]');
      const holder = form?.querySelector('[data-qt02-bank-rows]');
      target.closest('[data-qt02-bank-row]')?.remove();
      if (holder && !holder.querySelector('[data-qt02-bank-row]')) {
        holder.insertAdjacentHTML('beforeend', bankEntryRow());
      }
      updateBankPreview(form);
      return;
    }
    if (action === 'bank-demo-fill') {
      if (!bankDemoRows.length) return toast('Chưa có giao dịch chuyển khoản đủ mã tham chiếu để tạo dữ liệu mẫu.');
      if (!confirm('Điền sao kê mẫu từ các giao dịch đã ghi nhận? Thao tác này thay thế các dòng đang nhập. Dữ liệu mẫu chỉ dùng để kiểm thử, không phải sao kê ngân hàng thật.')) return;
      const form = target.closest('form[data-qt02-form="bank"]');
      const holder = form?.querySelector('[data-qt02-bank-rows]');
      if (!holder) return;
      holder.innerHTML = bankDemoRows.map(bankEntryRow).join('');
      const source = form.querySelector('[name="source"]');
      if (source) source.value = 'Sao kê mẫu kiểm thử';
      updateBankPreview(form);
      toast('Đã tạo sao kê mẫu. Kiểm tra dữ liệu trước khi lưu.');
      return;
    }

    if (action === 'open') {
      return postAndRefresh('reconciliation/', {date: day}, 'Đã mở kỳ đối soát.');
    }
    if (action === 'detect') {
      return postAndRefresh(`reconciliation/${day}/detect/`, {}, 'Đã kiểm tra và cập nhật ngoại lệ.');
    }
    if (action === 'ai-use-reason' || action === 'ai-use-action') {
      const card = target.closest('.qt02-exception');
      if (!card) return;
      const fieldName = action === 'ai-use-reason' ? 'reason' : 'proposedAction';
      const field = card.querySelector(`form[data-qt02-form="explain"] textarea[name="${fieldName}"]`);
      if (field && target.dataset.text) {
        field.value = target.dataset.text;
        field.focus();
        toast('Đã đưa gợi ý AI vào biểu mẫu. Nhân viên cần đọc và chỉnh lại trước khi gửi.');
      }
      return;
    }
    if (action === 'submit') {
      if (!confirm('Trình báo cáo đối soát ngày ' + day + ' cho Quản lý?')) return;
      return postAndRefresh(`reconciliation/${day}/submit/`, {}, 'Đã trình báo cáo.');
    }
    if (action === 'approve') {
      if (!confirm('Quản lý xác nhận duyệt báo cáo ngày ' + day + '?')) return;
      return postAndRefresh(`reconciliation/${day}/approve/`, {}, 'Đã phê duyệt báo cáo.');
    }
    if (action === 'return') {
      const reason = prompt('Lý do trả lại báo cáo để nhân viên bổ sung:');
      if (!reason) return;
      return postAndRefresh(`reconciliation/${day}/return/`, {reason}, 'Đã trả báo cáo.');
    }
    if (action === 'lock') {
      if (!confirm('Khóa sổ ngày ' + day + '? Sau khi khóa sổ, hệ thống không cho ghi thêm giao dịch vào ngày này.')) return;
      return postAndRefresh(`reconciliation/${day}/lock/`, {}, 'Đã khóa sổ và lưu snapshot.');
    }
    if (action === 'report') {
      window.location.href = `/api/reconciliation/${encodeURIComponent(day)}/report.csv`;
      return;
    }
    if (action === 'reminder-read') {
      return postAndRefresh(`reconciliation/reminders/${id}/read/`, {}, 'Đã đánh dấu thông báo đã xem.');
    }
    if (action === 'exception-approve' || action === 'exception-reject') {
      const feedback = prompt(action === 'exception-approve'
        ? 'Ý kiến Quản lý khi chấp nhận phương án:'
        : 'Nội dung yêu cầu nhân viên bổ sung:');
      if (!feedback) return;
      return postAndRefresh(
        `reconciliation/${day}/exceptions/${id}/decision/`,
        {decision: action === 'exception-approve' ? 'approve' : 'reject', feedback},
        action === 'exception-approve' ? 'Đã chấp nhận phương án ngoại lệ.' : 'Đã yêu cầu bổ sung.'
      );
    }
  }

  async function submitForm(form) {
    const values = Object.fromEntries(new FormData(form).entries());
    const day = selectedDay;
    if (form.dataset.qt02Form === 'cash') {
      return postAndRefresh(`reconciliation/${day}/cash/`, {
        openingCash: Number(values.openingCash),
        cashTransferOut: Number(values.cashTransferOut),
        countedCash: Number(values.countedCash),
        notes: values.notes
      }, 'Đã lưu kiểm đếm quỹ.');
    }
    if (form.dataset.qt02Form === 'bank') {
      const rows = [];
      const seen = new Set();
      for (const [index, entry] of [...form.querySelectorAll('[data-qt02-bank-row]')].entries()) {
        const field = name => String(entry.querySelector(`[name="${name}"]`)?.value || '').trim();
        const reference = field('reference');
        const amountText = field('amount');
        const description = field('description');
        const localTime = field('transactionAt');
        if (![reference, amountText, description, localTime].some(Boolean)) continue;
        if (reference.length < 3 || reference.length > 120) throw new Error(`Giao dịch dòng ${index + 1}: mã giao dịch cần từ 3 đến 120 ký tự.`);
        const uniqueRef = reference.toUpperCase();
        if (seen.has(uniqueRef)) throw new Error(`Giao dịch dòng ${index + 1}: mã ${reference} đã nhập trùng.`);
        seen.add(uniqueRef);
        const amount = Number(amountText);
        if (!amountText || !Number.isSafeInteger(amount) || amount === 0) {
          throw new Error(`Giao dịch dòng ${index + 1}: số tiền phải là số nguyên khác 0.`);
        }
        let transactionAt = null;
        if (localTime) {
          const parsed = new Date(localTime);
          if (Number.isNaN(parsed.getTime())) throw new Error(`Giao dịch dòng ${index + 1}: thời gian không hợp lệ.`);
          transactionAt = parsed.toISOString();
        }
        rows.push({reference, amount, description, transactionAt});
      }
      if (rows.length > 2000) throw new Error('Sao kê chỉ cho phép tối đa 2.000 giao dịch.');
      if (!rows.length && !confirm('Bạn đang lưu sao kê KHÔNG CÓ GIAO DỊCH. Tiếp tục?')) return;
      return postAndRefresh(`reconciliation/${day}/bank-statement/`, {
        source: values.source, rows
      }, 'Đã nhập sao kê ngân hàng.');
    }
    if (form.dataset.qt02Form === 'pending') {
      return postAndRefresh(`reconciliation/${day}/pending/${values.invoiceId}/`, {
        disposition: values.disposition, note: values.note
      }, 'Đã ghi nhận phương án khoản treo.');
    }
    if (form.dataset.qt02Form === 'ai-exception') {
      const exceptionId = values.exceptionId;
      const file = form.querySelector('input[name="evidenceFile"]')?.files?.[0];
      let uploaded = false;
      if (file) {
        await uploadExceptionEvidence(day, exceptionId, file);
        uploaded = true;
      }
      try {
        await api(`reconciliation/${day}/exceptions/${exceptionId}/ai/`, 'POST', {
          evidenceText: values.evidenceText || ''
        });
      } finally {
        if (uploaded) await fill();
      }
      await refresh();
      await fill();
      toast('AI đã đọc dữ liệu/chứng từ và đưa ra gợi ý. Nhân viên cần kiểm tra trước khi giải trình.');
      return;
    }
    if (form.dataset.qt02Form === 'explain') {
      return postAndRefresh(`reconciliation/${day}/exceptions/${values.exceptionId}/explain/`, {
        reason: values.reason, evidence: values.evidence, proposedAction: values.proposedAction
      }, 'Đã gửi giải trình cho Quản lý.');
    }
  }

  document.addEventListener('click', async event => {
    const target = event.target.closest('[data-qt02-action]');
    if (!target) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    try {
      await clickAction(target.dataset.qt02Action, target.dataset.id || '', target);
    } catch (error) {
      errorHandler(error);
    }
  }, true);

  document.addEventListener('input', event => {
    const form = event.target.closest('form[data-qt02-form="bank"]');
    if (form) updateBankPreview(form);
  }, true);

  document.addEventListener('submit', async event => {
    const form = event.target.closest('form[data-qt02-form]');
    if (!form) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const button = form.querySelector('[type="submit"]');
    if (button) button.disabled = true;
    try {
      await submitForm(form);
    } catch (error) {
      errorHandler(error);
    } finally {
      if (button?.isConnected) button.disabled = false;
    }
  }, true);

  window.PitchProReconciliation = {page, fill};
})();
