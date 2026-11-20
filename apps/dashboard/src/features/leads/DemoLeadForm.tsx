'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { runDemoLead, type DemoLeadChoices, type DemoLeadResult } from '@/services/demoLeads';
import { downloadDemoLeadReport } from '@/services/demoLeadReport';
import { demoLeadExamples, demoLeadExampleChoices, type DemoLeadExampleId } from '@/services/demoLeadPresets';
import styles from './DemoLeadForm.module.css';

export function DemoLeadForm() {
  const [choices, setChoices] = useState<DemoLeadChoices>({ budget: '1500000', location: 'Business Bay', bedrooms: 1, timeline: 3, purpose: 'investment' });
  const [result, setResult] = useState<DemoLeadResult | null>(null);
  const [error, setError] = useState('');
  const [retryNotice, setRetryNotice] = useState('');
  const [downloadNotice, setDownloadNotice] = useState('');
  const [freshNotice, setFreshNotice] = useState('');
  const [focusRequest, setFocusRequest] = useState(0);
  const budgetInput = useRef<HTMLInputElement>(null);
  useEffect(() => { if (focusRequest > 0) budgetInput.current?.focus(); }, [focusRequest]);
  const [busy, setBusy] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const submittedChoices = useRef<DemoLeadChoices | null>(null);
  const identity = useRef<string | null>(null);
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (active.current) return;
    const controller = new AbortController();
    active.current = controller;
    setFreshNotice(''); setBusy(true); setAttempted(true); setError(''); setRetryNotice(''); setDownloadNotice('');
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      identity.current ??= crypto.randomUUID();
      submittedChoices.current ??= { ...choices };
      const output = await runDemoLead(submittedChoices.current, identity.current, controller.signal);
      if (!controller.signal.aborted) {
        if (output.duplicate && result && !result.duplicate) {
          setRetryNotice('Duplicate retry stopped. The earlier qualification score, reasons and routing queue are kept below. No second mock CRM write was made.');
        } else { setResult(output); }
      }
    } catch {
      setError(controller.signal.aborted
        ? 'The request stopped before a result arrived. It may have finished on the API. Running the same demo again will check for a duplicate.'
        : 'Could not run the demo. Start the updated local API in demo mode, then try again.');
    } finally {
      clearTimeout(timer); active.current = null; setBusy(false);
    }
  }

  function reset() {
    if (active.current) return;
    setFreshNotice('');
    identity.current = null; submittedChoices.current = null; setAttempted(false); setDownloadNotice(''); setRetryNotice(''); setResult(null); setError('');
  }
  function newLead() {
    if (active.current) return;
    reset();
    setFreshNotice('New fictional lead ready. Requirements are editable; existing mock records are unchanged.');
    setFocusRequest(previous => previous + 1);
  }
  function example(id: DemoLeadExampleId) {
    if (active.current) return;
    const next = demoLeadExampleChoices(id);
    reset(); setChoices(next);
  }

  function download() {
    if (busy || !result || !submittedChoices.current) return;
    try { downloadDemoLeadReport(submittedChoices.current, result); setDownloadNotice('Lead report prepared. Check your browser downloads.'); }
    catch { setDownloadNotice('Could not prepare the download. Your qualification result is still available.'); }
  }

  return (
    <section className={`panel ${styles.panel}`} aria-labelledby="demo-lead-title">
      <div className="panel-header"><h2 id="demo-lead-title" className="panel-title">Try demo lead</h2><span className={styles.tag}>Fictional data only</span></div>
      <p className={styles.description}>Choose a scenario and see how the agents qualify and route it. A fictional contact is generated automatically. No messages are sent. After a run, choose New fictional lead to edit the requirements. Duplicate retries keep the earlier qualification details. Download a readable qualification report after a run. Starting a new lead returns focus to the budget field.</p>
      <p className={styles.description}>Select a fictional lead example to start fresh and fill the requirements. Edit them if needed, then select Run demo qualification. Selecting an example makes no request.</p>
      <div className={styles.actions} role="group" aria-label="Fictional lead examples">{demoLeadExamples.map(item => <button className="btn" type="button" key={item.id} disabled={busy} onClick={() => example(item.id)}>{item.label}</button>)}</div>
      <form onSubmit={submit}>
        <fieldset className={styles.fields} disabled={busy || attempted} aria-describedby={attempted ? "demo-lead-lock-note" : undefined}>
          <legend className={styles.legend}>Demo requirements</legend>
          <label>Maximum budget (AED)<input ref={budgetInput} type="number" min="1" max="9999999999" step="1" required value={choices.budget} onChange={e => setChoices({ ...choices, budget: e.target.value })} /></label>
          <label>Location<select value={choices.location} onChange={e => setChoices({ ...choices, location: e.target.value })}>{['Business Bay', 'Dubai Marina', 'Jumeirah Village Circle'].map(value => <option key={value}>{value}</option>)}</select></label>
          <label>Bedrooms<select value={choices.bedrooms} onChange={e => setChoices({ ...choices, bedrooms: Number(e.target.value) })}>{[0, 1, 2, 3, 4, 5].map(value => <option value={value} key={value}>{value === 0 ? 'Studio' : value}</option>)}</select></label>
          <label>Buying timeline<select value={choices.timeline} onChange={e => setChoices({ ...choices, timeline: Number(e.target.value) })}>{[1, 3, 6, 12].map(value => <option value={value} key={value}>{value} months</option>)}</select></label>
          <label>Purpose<select value={choices.purpose} onChange={e => setChoices({ ...choices, purpose: e.target.value as DemoLeadChoices['purpose'] })}><option value="investment">Investment</option><option value="end_use">Own home</option></select></label>
        </fieldset>
        {attempted && <p id="demo-lead-lock-note" className={styles.description}>Requirements are locked for this fictional lead. Retrying keeps the same contact and requirements. Choose New fictional lead to edit them.</p>}
        <div className={styles.actions}>
          <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Running agents…' : 'Run demo qualification'}</button>
          <button className="btn" type="button" disabled={busy} onClick={newLead}>New fictional lead</button>
        </div>
      </form>
      <p aria-label="New fictional lead feedback" aria-live="polite" aria-atomic="true">{freshNotice}</p>
      {busy && <p role="status">Validating the demo environment and processing your fictional lead…</p>}
      {retryNotice && <p role="status" className={styles.description}>{retryNotice}</p>}
      {error && <p role="alert" className={styles.error}>{error}</p>}
      {result && <div className={styles.result} role="status" aria-live="polite">
        <h3>{result.duplicate ? 'Duplicate demo detected' : 'Demo qualification complete'}</h3>
        <button className="btn" type="button" disabled={busy} onClick={download}>Download lead report</button>
        {downloadNotice && <p>{downloadNotice}</p>}
        {result.duplicate ? <p>This fictional contact was already processed. The agents skipped qualification and another CRM write. Choose “New fictional lead” for a different scenario.</p> : <>
          <dl className={styles.summary}><div><dt>Score</dt><dd>{result.score} / 100</dd></div><div><dt>Category</dt><dd>{result.category}</dd></div><div><dt>Routing queue</dt><dd>{result.queue}</dd></div></dl>
          <h4>Why this score</h4><ul>{result.factors.map((factor, index) => <li key={index}>{factor.reason} <strong>({factor.points} points)</strong></li>)}</ul>
        </>}
        <details><summary>Workflow steps</summary><ol>{result.steps.map((step, index) => <li key={index}>{step.name.replaceAll('_', ' ')} — {step.status}</li>)}</ol></details>
        <p className={styles.description}>This result comes from the API’s mock workflow. The sample table below stays unchanged. In-memory demo records disappear when the API restarts.</p>
      </div>}
    </section>
  );
}
