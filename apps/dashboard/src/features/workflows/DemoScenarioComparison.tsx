'use client';

import { useEffect, useRef, useState } from 'react';
import { downloadScenarioComparison } from '@/services/demoScenarioComparisonReport';
import type { ScenarioSnapshot } from '@/services/demoScenarioHistory';
import styles from './DemoScenarioComparison.module.css';

export function DemoScenarioComparison({ items, busy, onClear }: { items: ScenarioSnapshot[]; busy: boolean; onClear: () => void }) {
  const [notice, setNotice] = useState('');
  const [selectionNotice, setSelectionNotice] = useState('');
  const previousItems = useRef(items);
  useEffect(() => {
    const previous = previousItems.current;
    previousItems.current = items;
    if (items.some(item => !previous.some(saved => saved.key === item.key))) {
      setSelectionNotice(`Scenario added to comparison. ${items.length} of 3 saved.${previous.length === 3 ? ' Oldest comparison removed; latest three retained.' : ''}`);
    } else if (previous.length > 0 && items.length === 0) {
      setSelectionNotice('Comparison cleared. Current scenario result and mock CRM records are unchanged.');
    }
  }, [items]);
  useEffect(() => setNotice(''), [items]);
  function download() {
    if (busy || !items.length) return;
    try { downloadScenarioComparison(items); setNotice('Comparison report prepared. Check your browser downloads.'); }
    catch { setNotice('Could not prepare the download. Your comparison is still available.'); }
  }
  return <section className={styles.comparison} aria-labelledby="demo-comparison-title">
    <div className={styles.header}><h3 id="demo-comparison-title">Compare recent demo scenarios</h3><button type="button" className="btn" disabled={busy || items.length === 0} onClick={onClear}>Clear comparison</button></div>
    <p>Shows up to three runs, newest first. Kept only while this page stays open. Clearing this comparison does not remove mock CRM records. Comparison changes are announced below.</p>
    <p aria-label="Scenario comparison feedback" aria-live="polite" aria-atomic="true">{selectionNotice}</p>
    <button type="button" className="btn" disabled={busy || !items.length} onClick={download}>Download comparison report</button>
    {notice && <p role="status">{notice}</p>}
    {items.length === 0 ? <p>Run a new fictional scenario to begin comparing. Duplicate retries are not added.</p> : <div className={styles.scroll} tabIndex={0} role="region" aria-label="Recent fictional scenario comparison"><table>
      <caption>Fictional scenario results — newest first</caption>
      <thead><tr><th scope="col">Requirements</th><th scope="col">Qualification</th><th scope="col">Fictional property matches</th><th scope="col">Reply outcome</th></tr></thead>
      <tbody>{items.map(item => <tr key={item.key}>
        <td><strong>AED {Number(item.choices.budget).toLocaleString('en-AE')}</strong><br/>{item.choices.location}<br/>{item.choices.bedrooms === 0 ? 'Studio' : `${item.choices.bedrooms} bedroom(s)`}</td>
        <td>{item.score}/100 · {item.category}<br/>{item.queue}</td>
        <td>{item.matches.length === 0 ? 'No fictional matches' : <ul>{item.matches.map((match, index) => <li key={index}><strong>Match: {match.name}</strong><br/>{match.price === null ? 'Price not confirmed' : `AED ${Number(match.price).toLocaleString('en-AE')}`}<br/>Source: demo-seed · As of {match.date}</li>)}</ul>}</td>
        <td>{item.outcome === 'completed' ? 'Unsent draft; human review required' : 'Skipped — no matches'}</td>
      </tr>)}</tbody>
    </table></div>}
    <p>Fictional demo only. Prices, availability, payment plans and handover dates require developer confirmation. No investment return is implied or guaranteed. Nothing was sent or booked.</p>
  </section>;
}
