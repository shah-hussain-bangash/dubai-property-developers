'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { askDemoKnowledge, type DemoKnowledgeResult } from '@/services/demoKnowledge';
import { downloadDemoKnowledgeReport } from '@/services/demoKnowledgeReport';
import styles from './DemoKnowledgeForm.module.css';

export function DemoKnowledgeForm() {
  const [question, setQuestion] = useState('Demo Creek Heights payment plan');
  const [result, setResult] = useState<DemoKnowledgeResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [changed, setChanged] = useState(false);
  const [clearNotice, setClearNotice] = useState('');
  const input = useRef<HTMLTextAreaElement>(null);
  const [downloadNotice, setDownloadNotice] = useState('');
  const answeredQuestion = useRef<string | null>(null);
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (active.current) return;
    const controller = new AbortController(); active.current = controller;
    setClearNotice(''); setBusy(true); setResult(null); setError(''); setChanged(false); setDownloadNotice(''); answeredQuestion.current = null;
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const submittedQuestion = question.trim();
      const answer = await askDemoKnowledge(submittedQuestion, controller.signal);
      if (!controller.signal.aborted) { answeredQuestion.current = submittedQuestion; setResult(answer); }
    } catch { setError('Could not check the demo documents. Check the updated local API and try again manually.'); }
    finally { clearTimeout(timer); active.current = null; setBusy(false); }
  }
  function sample(text: string) {
    if (active.current) return;
    setClearNotice('');
    if (result) setChanged(true);
    setQuestion(text); setResult(null); setError(''); setDownloadNotice(''); answeredQuestion.current = null;
  }
  function clearDraft() {
    if (active.current) return;
    sample(''); setChanged(false);
    setClearNotice('Question and draft cleared. Nothing was sent.');
    input.current?.focus();
  }
  function download() {
    if (busy || !result || !answeredQuestion.current) return;
    try { downloadDemoKnowledgeReport(answeredQuestion.current, result); setDownloadNotice('Knowledge report prepared. Check your browser downloads.'); }
    catch { setDownloadNotice('Could not prepare the download. Your demo answer is still available.'); }
  }
  return <section className={'panel ' + styles.panel} aria-labelledby="demo-knowledge-title">
    <div className="panel-header"><h2 id="demo-knowledge-title" className="panel-title">Ask demo knowledge</h2><span className={styles.tag}>Public fictional documents only</span></div>
    <p className={styles.description}>Ask about the demo buying process, viewings or payment plan. Replies quote fictional documents and need human review before sharing. Keep real customer details out of demo questions. Editing clears the earlier draft and citations. Download a readable answer and citation report after asking a question.</p>
    <form onSubmit={submit}>
      <fieldset className={styles.fields} disabled={busy}>
        <legend className={styles.legend}>Demo document question</legend>
        <label htmlFor="demo-knowledge-question">Question about demo documents</label>
        <textarea ref={input} id="demo-knowledge-question" minLength={3} maxLength={1000} required rows={3} value={question} onChange={e => sample(e.target.value)} />
        <div className={styles.samples} aria-label="Example questions">
          <button className="btn" type="button" onClick={() => sample('Demo Creek Heights payment plan')}>Payment plan example</button>
          <button className="btn" type="button" onClick={() => sample('Viewings scheduled with an advisor')}>Viewing example</button>
          <button className="btn" type="button" onClick={() => sample('zzqx unrelated vocabulary')}>No-answer example</button>
        </div>
      </fieldset>
      <div className={styles.actions}><button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Checking demo sources…' : 'Ask demo question'}</button><button className="btn" type="button" disabled={busy} onClick={clearDraft}>Clear demo question</button></div>
    </form>
    <p aria-label="Clear demo question feedback" aria-live="polite" aria-atomic="true">{clearNotice}</p>
    {changed && <p role="status" className={styles.description}>Question changed. Choose Ask demo question to check the demo sources again.</p>}
    {busy && <p role="status" className={styles.description}>Checking public demo documents…</p>}
    {error && <p role="alert" className={styles.error}>{error}</p>}
    {result && <div role="status" aria-live="polite" className={styles.result}>
      <h3>{result.needsHuman ? 'Human handoff needed' : 'Draft answer — review before sharing'}</h3>
      <button className="btn" type="button" disabled={busy} onClick={download}>Download knowledge report</button>
      {downloadNotice && <p>{downloadNotice}</p>}
      {result.answer ? <p className={styles.answer}>{result.answer}</p> : <p>No sufficiently relevant public demo passage was found. Ask a staff member to review this question.</p>}
      {result.notes.length > 0 && <ul>{result.notes.map((note, index) => <li key={index}>{note}</li>)}</ul>}
      {result.citations.length > 0 && <div><h4>Cited fictional sources</h4>{result.citations.map((citation, index) => <article className={styles.citation} key={citation.id + index}>
        <h5>{citation.title}</h5><p className={styles.source}>Document version {citation.version}</p><blockquote>{citation.excerpt}</blockquote>
      </article>)}</div>}
      <p className={styles.footnote}>This is a demo draft, not a sent message or an approved customer reply. The sample document table below is separate.</p>
    </div>}
  </section>;
}
