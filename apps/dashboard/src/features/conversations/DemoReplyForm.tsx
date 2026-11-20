'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { prepareDemoReply, type DemoReply } from '@/services/demoConversations';
import { downloadDemoReplyReport } from '@/services/demoReplyReport';
import styles from './DemoReplyForm.module.css';

export function DemoReplyForm() {
  const [message, setMessage] = useState('What is the payment plan for Demo Creek Heights?');
  const [result, setResult] = useState<DemoReply | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [changed, setChanged] = useState(false);
  const [clearNotice, setClearNotice] = useState('');
  const input = useRef<HTMLTextAreaElement>(null);
  const [downloadNotice, setDownloadNotice] = useState('');
  const repliedMessage = useRef<string | null>(null);
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (active.current) return;
    const controller = new AbortController(); active.current = controller;
    setClearNotice(''); setBusy(true); setResult(null); setError(''); setChanged(false); setDownloadNotice(''); repliedMessage.current = null;
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const submittedMessage = message.trim();
      const reply = await prepareDemoReply(submittedMessage, controller.signal);
      if (!controller.signal.aborted) { repliedMessage.current = submittedMessage; setResult(reply); }
    } catch { setError('Could not prepare the demo reply. Check the updated local API and try again manually.'); }
    finally { clearTimeout(timer); active.current = null; setBusy(false); }
  }
  function sample(text: string) {
    if (active.current) return;
    setClearNotice('');
    if (result) setChanged(true);
    setMessage(text); setResult(null); setError(''); setDownloadNotice(''); repliedMessage.current = null;
  }
  function clearDraft() {
    if (active.current) return;
    sample(''); setChanged(false);
    setClearNotice('Message and draft cleared. Nothing was sent.');
    input.current?.focus();
  }
  function download() {
    if (busy || !result || !repliedMessage.current) return;
    try { downloadDemoReplyReport(repliedMessage.current, result); setDownloadNotice('Reply report prepared. Check your browser downloads.'); }
    catch { setDownloadNotice('Could not prepare the download. Your unsent draft is still available.'); }
  }
  return <section className={'panel ' + styles.panel} aria-labelledby="demo-reply-title">
    <div className="panel-header"><h2 id="demo-reply-title" className="panel-title">Try a demo sales reply</h2><span className={styles.tag}>Draft only · nothing is sent</span></div>
    <p className={styles.description}>See how the sales agent responds to a fictional web-chat message. It prepares a template-based draft or asks staff to take over. Keep real customer details out of this demo. Editing clears the earlier draft and citations. Download a readable unsent draft and citation report after preparing a reply.</p>
    <form onSubmit={submit}>
      <fieldset className={styles.fields} disabled={busy}>
        <legend className={styles.legend}>Fictional customer message</legend>
        <label htmlFor="demo-customer-message">Message from a fictional customer</label>
        <textarea ref={input} id="demo-customer-message" minLength={3} maxLength={4096} required rows={3} value={message} onChange={e => sample(e.target.value)} />
        <div className={styles.samples} aria-label="Example messages">
          <button className="btn" type="button" onClick={() => sample('What is the payment plan for Demo Creek Heights?')}>Payment plan example</button>
          <button className="btn" type="button" onClick={() => sample('This is a complaint about my booking')}>Complaint example</button>
          <button className="btn" type="button" onClick={() => sample('Unsubscribe, stop contacting me')}>Stop-contact example</button>
        </div>
      </fieldset>
      <div className={styles.actions}><button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Preparing demo draft…' : 'Prepare demo reply'}</button><button className="btn" type="button" disabled={busy} onClick={clearDraft}>Clear demo message</button></div>
    </form>
    <p aria-label="Clear demo message feedback" aria-live="polite" aria-atomic="true">{clearNotice}</p>
    {changed && <p role="status" className={styles.description}>Message changed. Choose Prepare demo reply to create an updated unsent draft.</p>}
    {busy && <p role="status" className={styles.description}>Preparing an unsent demo draft…</p>}
    {error && <p role="alert" className={styles.error}>{error}</p>}
    {result && <div className={styles.result} role="status" aria-live="polite">
      <h3>{result.needsHuman ? 'Staff handoff required' : 'Draft ready for human review'}</h3>
      <button className="btn" type="button" disabled={busy} onClick={download}>Download reply report</button>
      {downloadNotice && <p>{downloadNotice}</p>}
      <p className={styles.tag}>Unsent demo · {result.intent.replaceAll('_', ' ')} · {result.language === 'ar' ? 'Arabic' : 'English'}</p>
      {result.reason && <p className={styles.reason}>{result.reason}</p>}
      <h4>{result.needsHuman ? 'Unsent acknowledgement draft' : 'Unsent reply draft'}</h4>
      <blockquote className={styles.draft} dir={result.language === 'ar' ? 'rtl' : 'auto'} lang={result.language}>{result.text}</blockquote>
      {result.citations.length > 0 && <div><h4>Cited fictional sources</h4>{result.citations.map((citation, index) => <article className={styles.citation} key={citation.id + index}>
        <h5>{citation.title}</h5><p className={styles.source}>Document version {citation.version}</p><blockquote>{citation.excerpt}</blockquote>
      </article>)}</div>}
      <p className={styles.footnote}>No message, appointment or consent update was sent to a live service. This panel does not create an approval-queue entry. The sample conversation list below stays separate.</p>
    </div>}
  </section>;
}
