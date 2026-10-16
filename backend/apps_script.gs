// Mondo Noleggio – collegamento app → foglio "modulo noleggio"
// Incolla tutto in Estensioni → Apps Script, poi Esegui il deployment → Nuovo deployment → App web
// Esegui come: Me · Chi ha accesso: Chiunque
const TOKEN = '021dee45385e24db3f807670a1957c32';

function doPost(e) {
  const body = JSON.parse(e.postData.contents);
  if (body.token !== TOKEN) return out({ ok: false, error: 'unauthorized' });
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const sh = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
    const data = sh.getDataRange().getValues();
    let hr = -1, hc = -1;
    for (let r = 0; r < data.length && hr < 0; r++) {
      const c = data[r].indexOf('ID Noleggio');
      if (c >= 0) { hr = r; hc = c; }
    }
    if (hr < 0) return out({ ok: false, error: 'registro non trovato' });

    if (body.action === 'append') {
      let row = -1, maxN = 0;
      for (let r = hr + 1; r < data.length; r++) {
        const m = String(data[r][hc] || '').match(/NOL-(\d+)/);
        if (m) maxN = Math.max(maxN, Number(m[1]));
        if (row < 0 && !data[r][hc + 1] && !data[r][hc + 2]) row = r;
      }
      if (row < 0) row = data.length;
      let id = String((data[row] || [])[hc] || '');
      if (!/^NOL-/.test(id)) id = 'NOL-' + String(maxN + 1).padStart(3, '0');
      sh.getRange(row + 1, hc + 1, 1, 9).setValues([[id, body.unit_id, body.customer, body.phone, body.email,
        body.start, body.end, body.amount, body.status]]);
      return out({ ok: true, sheet_id: id });
    }
    if (body.action === 'update') {
      for (let r = hr + 1; r < data.length; r++) {
        if (String(data[r][hc]) === body.sheet_id) {
          sh.getRange(r + 1, hc + 9).setValue(body.status);
          return out({ ok: true });
        }
      }
      return out({ ok: false, error: 'not found' });
    }
    return out({ ok: false, error: 'unknown action' });
  } finally {
    lock.releaseLock();
  }
}

function out(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
