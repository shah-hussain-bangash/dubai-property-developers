'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { matchDemoProperties, type DemoPropertyMatch, type DemoPropertyChoices, type DemoPropertyResult } from '@/services/demoProperties';
import { toggleDemoShortlist } from '@/services/demoPropertyShortlist';
import { LocalPropertyExplanation } from './LocalPropertyExplanation';
import { DemoPropertyShortlist } from './DemoPropertyShortlist';
import { demoPropertyExamples, demoPropertyExampleChoices } from '@/services/demoPropertyPresets';
import { downloadPropertySearchReport } from '@/services/demoPropertySearchReport';
import styles from './DemoPropertyForm.module.css';

export function DemoPropertyForm() {
  const [choices, setChoices] = useState<DemoPropertyChoices>({ budget: '2000000', location: 'any', bedrooms: 'any', paymentPlan: false });
  const [result, setResult] = useState<DemoPropertyResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [changed, setChanged] = useState(false);
  const [downloadNotice, setDownloadNotice] = useState('');
  const matchedChoices = useRef<DemoPropertyChoices | null>(null);
  const [shortlist, setShortlist] = useState<DemoPropertyMatch[]>([]);
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);

  function changeChoices(next: DemoPropertyChoices) {
    if (active.current) return;
    if (result) setChanged(true);
    setChoices(next); setResult(null); setError(''); setDownloadNotice(''); matchedChoices.current = null;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (active.current) return;
    const controller = new AbortController(); active.current = controller;
    setBusy(true); setResult(null); setError(''); setChanged(false); setDownloadNotice(''); matchedChoices.current = null;
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const submitted = { ...choices };
      const output = await matchDemoProperties(submitted, controller.signal);
      if (!controller.signal.aborted) { matchedChoices.current = submitted; setResult(output); }
    } catch {
      setError('Could not match demo properties. Check the updated local API and try again manually.');
    } finally { clearTimeout(timer); active.current = null; setBusy(false); }
  }
  function download() {
    if (busy || !result || !matchedChoices.current) return;
    try { downloadPropertySearchReport(matchedChoices.current, result); setDownloadNotice('Search report prepared. Check your browser downloads.'); }
    catch { setDownloadNotice('Could not prepare the download. Your search result is still available.'); }
  }
  return <section className={'panel ' + styles.panel} aria-labelledby="demo-property-title">
    <div className="panel-header"><h2 id="demo-property-title" className="panel-title">Try property matching</h2><span className={styles.tag}>Fictional catalog only</span></div>
    <p className={styles.description}>See how the recommendation agent ranks demo listings. Prices are illustrative, availability needs confirmation, and match scores use demo rules. Changing requirements clears earlier matches; your shortlist stays available. Unconfirmed prices do not establish budget fit. Unknown availability must be confirmed before offering.</p>
    <p className={styles.description}>Choose a fictional property example to fill the filters, then select Match demo properties. Selecting an example makes no request and keeps your shortlist. Download a search report after matching, including searches with no matches.</p>
    <div className={styles.actions} role="group" aria-label="Fictional property examples">{demoPropertyExamples.map(item => <button className="btn" type="button" key={item.id} disabled={busy} onClick={() => changeChoices(demoPropertyExampleChoices(item.id))}>{item.label}</button>)}</div>
    <form onSubmit={submit}>
      <fieldset className={styles.fields} disabled={busy}>
        <legend className={styles.legend}>Property matching requirements</legend>
        <label>Demo maximum budget (AED)<input type="number" min="1" max="9999999999" step="1" required value={choices.budget} onChange={e => changeChoices({ ...choices, budget: e.target.value })} /></label>
        <label>Preferred location<select value={choices.location} onChange={e => changeChoices({ ...choices, location: e.target.value })}><option value="any">Any location</option>{['Business Bay', 'Dubai Marina', 'Jumeirah Village Circle'].map(value => <option key={value}>{value}</option>)}</select></label>
        <label>Preferred bedrooms<select value={choices.bedrooms} onChange={e => changeChoices({ ...choices, bedrooms: e.target.value })}><option value="any">Any bedrooms</option>{[0, 1, 2, 3, 4, 5].map(value => <option value={value} key={value}>{value === 0 ? 'Studio' : value}</option>)}</select></label>
        <label className={styles.checkbox}><input type="checkbox" checked={choices.paymentPlan} onChange={e => changeChoices({ ...choices, paymentPlan: e.target.checked })} />Payment plan required</label>
      </fieldset>
      <div className={styles.actions}><button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Matching demo propertiesâ€¦' : 'Match demo properties'}</button></div>
    </form>
    {changed && <p role="status" className={styles.description}>Requirements changed. Choose Match demo properties to see updated results. Saved shortlist items keep their earlier listing details.</p>}
    {busy && <p role="status" className={styles.description}>Checking the demo environment and ranking fictional listingsâ€¦</p>}
    {error && <p role="alert" className={styles.error}>{error}</p>}
    {result && <div className={styles.results} role="status" aria-live="polite">
      <h3>{result.matches.length ? result.matches.length + (result.matches.length === 1 ? ' demo match' : ' demo matches') : 'No matching demo properties'}</h3>
      <button className="btn" type="button" disabled={busy} onClick={download}>Download search report</button>
      {downloadNotice && <p>{downloadNotice}</p>}
      {!result.matches.length && <p>{result.noMatch}</p>}
      {result.matches.some(match => match.price === null) && <p className={styles.disclaimer}>Some returned listings have unconfirmed prices. Their budget fit cannot be verified until a price is confirmed.</p>}
      <div className={styles.cards}>{result.matches.map(match => <article key={match.id} className={styles.card}>
        <span className={styles.tag}>Fictional listing Â· {match.id}</span>
        <h4>{match.name}</h4><p>{match.community} Â· {match.bedrooms === 0 ? 'Studio' : match.bedrooms + (match.bedrooms === 1 ? ' bedroom' : ' bedrooms')}</p>
        <p className={styles.price}>{match.price === null ? 'Price needs confirmation' : 'Illustrative AED ' + Number(match.price).toLocaleString('en-US')}</p>
        {match.price === null && <p>Budget fit not verified: price is unconfirmed.</p>}
        {match.availability === 'unknown' && <p>Availability not verified: confirm before offering.</p>}
        <p>Demo match score: {Math.round(match.score * 100)} / 100</p>
        <button type="button" className="btn" disabled={busy || (shortlist.length >= 3 && !shortlist.some(item => item.id === match.id))} aria-pressed={shortlist.some(item => item.id === match.id)} aria-label={`${shortlist.some(item => item.id === match.id) ? 'Remove' : 'Add'} ${match.id} ${shortlist.some(item => item.id === match.id) ? 'from' : 'to'} shortlist`} onClick={() => setShortlist(previous => toggleDemoShortlist(previous, match))}>{shortlist.some(item => item.id === match.id) ? 'Remove from shortlist' : 'Add to shortlist'}</button>
        <h5>Why it matches</h5><ul>{match.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
        <h5>Confirm before quoting</h5><ul>{match.caveats.map((caveat, index) => <li key={index}>{caveat}</li>)}</ul>
        <p className={styles.source}>Source: demo-seed Â· Data as of {match.date} Â· Catalog status: {match.availability}</p>
      </article>)}</div>
      {result.matches.length > 0 && matchedChoices.current && <LocalPropertyExplanation choices={matchedChoices.current} matches={result.matches} />}
      <p className={styles.disclaimer}>{result.disclaimer}</p>
      <p className={styles.description}>These API results are separate from the static sample inventory below.</p>
    </div>}
    <DemoPropertyShortlist items={shortlist} busy={busy} onRemove={id => setShortlist(previous => previous.filter(item => item.id !== id))} onClear={() => setShortlist([])} />
  </section>;
}
