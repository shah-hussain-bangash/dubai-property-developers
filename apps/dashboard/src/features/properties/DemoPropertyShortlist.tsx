'use client';

import { useEffect, useRef, useState } from 'react';
import { downloadPropertyShortlist } from '@/services/demoPropertyShortlistReport';
import type { DemoPropertyMatch } from '@/services/demoProperties';
import styles from './DemoPropertyShortlist.module.css';

export function DemoPropertyShortlist({ items, busy, onRemove, onClear }: { items: DemoPropertyMatch[]; busy: boolean; onRemove: (id: string) => void; onClear: () => void }) {
  const [notice, setNotice] = useState('');
  const [selectionNotice, setSelectionNotice] = useState('');
  const previousItems = useRef(items);
  useEffect(() => {
    const previous = previousItems.current;
    previousItems.current = items;
    const added = items.find(item => !previous.some(saved => saved.id === item.id));
    const removed = previous.find(item => !items.some(saved => saved.id === item.id));
    if (!added && !removed) return;
    const action = added ? `Added ${added.name}.` : items.length === 0 && previous.length > 1
      ? 'Shortlist cleared.' : `Removed ${removed!.name}.`;
    setSelectionNotice(`${action} Shortlist: ${items.length} of 3.`);
  }, [items]);
  useEffect(() => setNotice(''), [items]);
  function download() {
    if (busy || !items.length) return;
    try { downloadPropertyShortlist(items); setNotice('Shortlist report prepared. Check your browser downloads.'); }
    catch { setNotice('Could not prepare the download. Your shortlist is still available.'); }
  }
  return <section className={styles.shortlist} aria-labelledby="demo-shortlist-title">
    <div className={styles.header}><h3 id="demo-shortlist-title">Fictional property shortlist ({items.length}/3)</h3><button className="btn" type="button" disabled={busy || !items.length} onClick={onClear}>Clear shortlist</button></div>
    <p>Keep up to three fictional results from your searches. This shortlist clears when you leave or reload the page. Match scores reflect each search’s criteria. Shortlist changes are announced below.</p>
    <p aria-label="Shortlist selection feedback" aria-live="polite" aria-atomic="true">{selectionNotice}</p>
    {items.length === 3 && <p>Shortlist full: remove a saved property before adding another.</p>}
    <button className="btn" type="button" disabled={busy || !items.length} onClick={download}>Download shortlist report</button>
    {notice && <p role="status">{notice}</p>}
    {!items.length ? <p>Match demo properties, then choose Add to shortlist on a result.</p> : <div className={styles.scroll} role="region" aria-label="Fictional property shortlist comparison" tabIndex={0}>
      <table><caption>Saved fictional matches · source snapshots from earlier searches</caption><thead><tr><th scope="col">Property</th><th scope="col">Illustrative price</th><th scope="col">Source and status</th><th scope="col">Reasons and caveats</th><th scope="col">Action</th></tr></thead>
        <tbody>{items.map(item => <tr key={item.id}><td><strong>Shortlisted: {item.name}</strong><br/>{item.community}<br/>{item.bedrooms === 0 ? 'Studio' : `${item.bedrooms} bedroom(s)`}<br/>Demo match score: {Math.round(item.score * 100)}/100</td>
          <td>{item.price === null ? <><span>Price needs confirmation</span><br/><span>Budget fit not verified: price is unconfirmed.</span></> : `Illustrative AED ${Number(item.price).toLocaleString('en-US')}`}</td>
          <td>Source: demo-seed<br/>Data as of {item.date}<br/>Catalog status: {item.availability}{item.availability === 'unknown' && <><br/><span>Availability not verified: confirm before offering.</span></>}</td>
          <td><ul>{item.reasons.map((reason, index) => <li key={'r'+index}>{reason}</li>)}{item.caveats.map((caveat, index) => <li key={'c'+index}>{caveat}</li>)}</ul></td>
          <td><button className="btn" type="button" disabled={busy} aria-label={`Remove saved ${item.id} from shortlist`} onClick={() => onRemove(item.id)}>Remove</button></td>
        </tr>)}</tbody>
      </table>
    </div>}
    <p>Fictional demo only. Prices, availability, payment plans and handover dates must be confirmed with the developer. No investment return is implied or guaranteed. Shortlisting does not reserve a property or send an enquiry.</p>
  </section>;
}
