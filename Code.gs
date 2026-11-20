// Google Apps Script: receives the transcript from GitHub and saves it into your Drive folder.
// 1) Put your RadioScreener folder ID below (the long text at the end of the folder's web address).
// 2) Make up a long random SECRET (30+ letters and numbers). Use the same text in GitHub.
const FOLDER_ID = 'PASTE_FOLDER_ID_HERE';
const SECRET = 'PASTE_YOUR_LONG_RANDOM_SECRET_HERE';

function doPost(e) {
  try {
    const d = JSON.parse(e.postData.contents);
    if (d.secret !== SECRET) return reply({ ok: false, error: 'bad secret' });
    if (!/^[A-Za-z0-9_.-]+\.txt$/.test(d.name)) return reply({ ok: false, error: 'bad name' });
    if (typeof d.content !== 'string' || d.content.length > 2000000) return reply({ ok: false, error: 'bad content' });
    const folder = DriveApp.getFolderById(FOLDER_ID);
    const it = folder.getFilesByName(d.name);
    let f;
    if (it.hasNext()) { f = it.next(); f.setContent(d.content); }
    else { f = folder.createFile(d.name, d.content, MimeType.PLAIN_TEXT); }
    return reply({ ok: true, id: f.getId() });
  } catch (err) {
    return reply({ ok: false, error: String(err) });
  }
}

function reply(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
