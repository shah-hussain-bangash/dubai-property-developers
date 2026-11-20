'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { runScenario, type ScenarioResult } from '@/services/demoScenario';
import { downloadScenarioReport } from '@/services/demoScenarioReport';
import { downloadScenarioText } from '@/services/demoScenarioTextReport';
import { rememberScenario, type ScenarioSnapshot } from '@/services/demoScenarioHistory';
import { DemoScenarioComparison } from './DemoScenarioComparison';
import { scenarioExamples, scenarioExampleChoices, type ScenarioExampleId } from '@/services/demoScenarioPresets';
import { DemoQualificationBreakdown } from './DemoQualificationBreakdown';
import styles from './DemoScenarioForm.module.css';

export function DemoScenarioForm() {
  const [budget, setBudget] = useState('2000000');
  const [location, setLocation] = useState('Business Bay');
  const [bedrooms, setBedrooms] = useState(1);
  const [result, setResult] = useState<ScenarioResult | null>(null);
  const [freshNotice, setFreshNotice] = useState('');
  const [focusRequest, setFocusRequest] = useState(0);
  const budgetInput = useRef<HTMLInputElement>(null);
  useEffect(() => { if (focusRequest > 0) budgetInput.current?.focus(); }, [focusRequest]);
  const [busy, setBusy] = useState(false);
  const [started, setStarted] = useState(false);
  const [error, setError] = useState('');
  const [downloadNotice, setDownloadNotice] = useState('');
  const [retryNotice, setRetryNotice] = useState('');
  const [history, setHistory] = useState<ScenarioSnapshot[]>([]);
  const identity = useRef<string | null>(null);
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (active.current) return;
    const controller = new AbortController(); active.current = controller;
    setFreshNotice(''); setBusy(true); setStarted(true); setError(''); setDownloadNotice(''); setRetryNotice('');
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      identity.current ??= crypto.randomUUID();
      const scenarioId = identity.current;
      const value = await runScenario({ budget, location, bedrooms }, identity.current, controller.signal);
      if (!controller.signal.aborted) {
        if (value.status === 'duplicate' && result && result.status !== 'duplicate') {
          setRetryNotice('Repeat stopped before matching. The earlier completed result and its reports are kept below. No second mock CRM write was made.');
        } else { setResult(value); }
        setHistory(previous => rememberScenario(previous, { budget, location, bedrooms }, value, scenarioId));
      }
    } catch { if (!controller.signal.aborted || active.current === controller) setError('Demo did not finish. A mock lead may already exist. Retrying the same scenario may report a duplicate.'); }
    finally { clearTimeout(timer); active.current = null; setBusy(false); }
  }
  function reset() { if (active.current) return; setFreshNotice(''); identity.current = null; setStarted(false); setRetryNotice(''); setResult(null); setError(''); setDownloadNotice(''); }
  function newScenario() {
    if (active.current) return;
    reset();
    setFreshNotice('New demo scenario ready. Requirements are editable; saved comparisons and mock records are unchanged.');
    setFocusRequest(previous => previous + 1);
  }
  function example(id: ScenarioExampleId) {
    if (busy) return;
    const choices = scenarioExampleChoices(id);
    reset(); setBudget(choices.budget); setLocation(choices.location); setBedrooms(choices.bedrooms);
  }
  function download(readable = false) {
    if (!result || busy) return;
    try {
      if (readable) downloadScenarioText({ budget, location, bedrooms }, result);
      else downloadScenarioReport({ budget, location, bedrooms }, result);
      setDownloadNotice('Demo report prepared for download. Check your browser downloads.');
    } catch { setDownloadNotice('Could not prepare the download. Your demo result is still available below.'); }
  }
  return <section className={'panel ' + styles.panel} aria-labelledby="demo-scenario-title">
    <div className="panel-header"><h2 id="demo-scenario-title" className="panel-title">Run a guided demo</h2><span className={styles.tag}>Fictional data · mock services</span></div>
    <p className={styles.description}>Follow one fictional investment enquiry through qualification, property matching and an unsent viewing reply. No appointment is booked or approval request created. Download a demo report after running a scenario. Readable text and JSON formats are available. Score explanations are available after each run. Downloads include the returned score rules and reasons. Repeating a completed scenario keeps its earlier result and reports. Starting a new scenario returns focus to the budget field.</p>
    <p className={styles.description}>Choose a fictional apartment example, then select Run guided demo. Selecting an example only fills the form; you can edit its requirements before running it.</p>
    <div className={styles.actions} role="group" aria-label="Fictional scenario examples">{scenarioExamples.map(item => <button type="button" className="btn" key={item.id} disabled={busy} onClick={() => example(item.id)}>{item.label}</button>)}</div>
    <form onSubmit={submit}>
      <fieldset className={styles.fields} disabled={busy || started}><legend className={styles.legend}>Fictional apartment requirements</legend>
        <label>Maximum budget (AED)<input ref={budgetInput} type="number" required min="1" max="9999999999" step="1" value={budget} onChange={e => setBudget(e.target.value)} /></label>
        <label>Location<select value={location} onChange={e => setLocation(e.target.value)}>{['Business Bay', 'Dubai Marina', 'Jumeirah Village Circle'].map(value => <option key={value}>{value}</option>)}</select></label>
        <label>Bedrooms<select value={bedrooms} onChange={e => setBedrooms(Number(e.target.value))}>{[0, 1, 2, 3, 4, 5].map(value => <option key={value} value={value}>{value === 0 ? 'Studio' : value}</option>)}</select></label>
      </fieldset>
      <div className={styles.actions}><button className="btn btn-primary" disabled={busy}>{busy ? 'Running demo…' : started ? 'Run same scenario' : 'Run guided demo'}</button><button type="button" className="btn" onClick={newScenario} disabled={busy}>New demo scenario</button></div>
    </form>
    <p aria-label="New demo scenario feedback" aria-live="polite" aria-atomic="true">{freshNotice}</p>
    {busy && <p role="status">Qualifying, matching and preparing an unsent draft…</p>}
    {retryNotice && <p role="status" className={styles.description}>{retryNotice}</p>}
    {error && <p role="alert" className={styles.error}>{error}</p>}
    {result && <div className={styles.result} role="status" aria-live="polite">
      <h3>{result.status === 'duplicate' ? 'Duplicate stopped before matching' : result.status === 'no_matches' ? 'No fictional properties match' : 'Demo completed — reply awaits review'}</h3>
      <button type="button" className="btn" disabled={busy} onClick={() => download()}>Download demo report</button>
      <button type="button" className="btn" disabled={busy} onClick={() => download(true)}>Download readable report</button>
      {downloadNotice && <p>{downloadNotice}</p>}
      <ol><li>Qualification: {result.lead.duplicate ? 'duplicate; no second mock CRM write' : `${result.lead.score}/100 · ${result.lead.category} · ${result.lead.queue}`}</li><li>Property matching: {result.properties ? `${result.properties.matches.length} fictional match(es)` : 'skipped'}</li><li>Viewing reply: {result.reply ? 'unsent; human review required' : 'skipped'}</li></ol>
      <DemoQualificationBreakdown lead={result.lead} />
      {result.properties && <><p>{result.properties.noMatch}</p>{result.properties.matches.map(match => <article className={styles.citation} key={match.id}><h4>{match.name}</h4><p>{match.community} · {match.bedrooms} bedroom(s) · {match.price ? `AED ${Number(match.price).toLocaleString('en-AE')}` : 'Price not confirmed'}</p><p>Source: demo-seed · As of {match.date}</p><ul>{match.reasons.map((v, i) => <li key={i}>{v}</li>)}</ul>{match.caveats.map((v, i) => <p key={i}>{v}</p>)}</article>)}<p>{result.properties.disclaimer}</p></>}
      {result.reply && <><h4>Unsent viewing reply</h4><blockquote className={styles.draft}>{result.reply.text}</blockquote><p>Human review required. Nothing was sent; no appointment was booked.</p></>}
    </div>}
    <DemoScenarioComparison items={history} busy={busy} onClear={() => setHistory([])} />
    <p className={styles.footnote}>Uses in-memory demo records. Existing sample tables stay separate. Restarting the demo API clears its records.</p>
  </section>;
}
