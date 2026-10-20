// Coolsville Poster: uploads new queue.json entries to YouTube once each.
// Apps Script project under coolsvilleaiposting@gmail.com. Needs the YouTube Data API
// advanced service enabled (Services > YouTube Data API v3). Run postQueue() once by hand
// to authorize, then add a time-driven trigger: postQueue, every hour.

const QUEUE_URL = 'https://raw.githubusercontent.com/coolsvilleaiposting-afk/Videos/main/queue.json';
const SHEET_ID = '1n1E6EZWAwrQoTWWx1ipalDEqdAJyfUl9l18ibI6s5FU';
const LOG_TAB = 'Posted';
const STALE_HOURS = 48;   // anything whose publish time is older than this is never uploaded
const MAX_ATTEMPTS = 3;

// Google's daily fetch quota: when it is used up, stop for this hour without counting an attempt.
function isQuota_(msg) {
  return /too many times|quota|Bandwidth|rate limit/i.test(String(msg));
}

function postQueue() {
  const log = logSheet_();
  const seen = seenIds_(log);
  let queue;
  try {
    queue = JSON.parse(UrlFetchApp.fetch(QUEUE_URL + '?t=' + Date.now(), {muteHttpExceptions: false}).getContentText());
  } catch (e) {
    if (isQuota_(e.message)) { console.log('quota used up, trying again next hour'); return; }
    throw e;
  }
  const now = new Date();
  let stop = false;
  queue.forEach(function (item) {
    if (stop) return;
    const id = String(item.id);
    const rec = seen[id];
    if (rec && (rec.videoId || rec.attempts >= MAX_ATTEMPTS || rec.status === 'stale')) return;
    const publishAt = new Date(item.publish_at);
    if (now.getTime() - publishAt.getTime() > STALE_HOURS * 3600 * 1000) {
      log.appendRow([id, item.title, item.publish_at, 'stale', '', 0, new Date()]);
      return;
    }
    const attempts = rec ? rec.attempts + 1 : 1;
    try {
      const blob = UrlFetchApp.fetch(item.video_url).getBlob().setName(id + '.mp4');
      const future = publishAt.getTime() > now.getTime() + 60 * 1000;
      // containsSyntheticMedia = YouTube's "altered or synthetic content" disclosure (the narration is a voice clone)
      const status = future
        ? {privacyStatus: 'private', publishAt: publishAt.toISOString(), selfDeclaredMadeForKids: false, containsSyntheticMedia: true}
        : {privacyStatus: 'public', selfDeclaredMadeForKids: false, containsSyntheticMedia: true};
      const res = YouTube.Videos.insert({
        snippet: {title: item.title, description: item.caption, categoryId: '20', tags: ['gaming history', 'did you know', 'shorts']},
        status: status
      }, 'snippet,status', blob);
      log.appendRow([id, item.title, item.publish_at, future ? 'scheduled' : 'published', res.id, attempts, new Date()]);
    } catch (e) {
      if (isQuota_(e.message)) { stop = true; console.log('quota used up at ' + id); return; }
      log.appendRow([id, item.title, item.publish_at, 'error: ' + e.message, '', attempts, new Date()]);
    }
  });
}

function logSheet_() {
  const ss = SpreadsheetApp.openById(SHEET_ID);
  let sh = ss.getSheetByName(LOG_TAB);
  if (!sh) {
    sh = ss.insertSheet(LOG_TAB);
    sh.appendRow(['queue_id', 'title', 'publish_at', 'status', 'youtube_id', 'attempts', 'logged_at']);
  }
  return sh;
}

// Latest record per queue id: {videoId, attempts, status}
function seenIds_(sh) {
  const rows = sh.getDataRange().getValues();
  const out = {};
  for (let i = 1; i < rows.length; i++) {
    const id = String(rows[i][0]);
    if (isQuota_(rows[i][3])) continue;   // quota failures never count against a video
    const prev = out[id] || {videoId: '', attempts: 0, status: ''};
    out[id] = {
      videoId: prev.videoId || String(rows[i][4] || ''),
      attempts: Math.max(prev.attempts, Number(rows[i][5] || 0)),
      status: String(rows[i][3] || '')
    };
  }
  return out;
}
