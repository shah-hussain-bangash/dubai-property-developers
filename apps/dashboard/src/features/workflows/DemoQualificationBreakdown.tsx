import type { DemoLeadResult } from '@/services/demoLeads';
import styles from './DemoQualificationBreakdown.module.css';

export function DemoQualificationBreakdown({ lead }: { lead: DemoLeadResult }) {
  return <details className={styles.breakdown}>
    <summary>Why this qualification score?</summary>
    <p>Qualification score and property availability are separate checks. A high score does not mean a property is available within the chosen budget.</p>
    {lead.duplicate ? <p>Duplicate detection stopped qualification. No new score was calculated.</p> : lead.factors.length === 0 ? <p>No rule breakdown was returned for this run.</p> : <div className={styles.scroll} role="region" aria-label="Qualification rule breakdown" tabIndex={0}>
      <table><caption>Points and reasons returned by the demo qualification workflow</caption>
        <thead><tr><th scope="col">Rule</th><th scope="col">Points</th><th scope="col">Reason</th></tr></thead>
        <tbody>{lead.factors.map((factor, index) => <tr key={index}><td>{factor.name.replaceAll('_', ' ')}</td><td>{factor.points > 0 ? '+' : ''}{factor.points}</td><td>{factor.reason}</td></tr>)}</tbody>
      </table>
    </div>}
    <p>These are the existing demo rules. The dashboard displays their returned values without changing the score or routing.</p>
  </details>;
}
