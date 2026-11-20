import styles from './DemoQuickStart.module.css';

const demos = [
  { href: '/workflows#demo-scenario-title', title: 'Run a guided scenario', description: 'Follow a fictional enquiry from qualification to property matching and an unsent viewing draft. Compare runs and download reports.' },
  { href: '/leads#demo-lead-title', title: 'Qualify a demo lead', description: 'Choose fictional requirements, inspect the score and routing, then download the qualification report.' },
  { href: '/properties#demo-property-title', title: 'Match demo properties', description: 'Search the fictional catalog, compare up to three shortlisted matches and save a shortlist report.' },
  { href: '/knowledge#demo-knowledge-title', title: 'Ask demo knowledge', description: 'Ask a question about public fictional documents and review an answer with source citations.' },
  { href: '/conversations#demo-reply-title', title: 'Prepare a demo sales reply', description: 'Create an unsent draft or see a staff handoff. Download the draft and citations for review.' },
];

export function DemoQuickStart() {
  return <section className={'panel ' + styles.panel} aria-labelledby="demo-quick-start-title">
    <div className="panel-header"><h2 className="panel-title" id="demo-quick-start-title">Try the demo</h2><span className={styles.tag}>Fictional data only</span></div>
    <p className={styles.intro}>Start with a guided scenario or explore an individual demo. Forms run only after you submit them. Mock services send no live messages or bookings.</p>
    <p className={styles.intro}><a className="btn" href="/local-demo-user-guide.txt" download="dubai-real-estate-ai-demo-guide.txt">Download demo guide</a></p>
    <p className={styles.intro}><a className="btn" href="/local-demo-checkpoint-step607.txt" download="dubai-real-estate-ai-checkpoint-step607.txt">Download verification summary</a> Step 607 evidence snapshot; this download does not check current service availability or live readiness.</p>
    <nav aria-label="Interactive fictional demos"><ul className={styles.links}>{demos.map(demo => <li key={demo.href}><a href={demo.href} className={styles.link}><strong>{demo.title}</strong><span>{demo.description}</span></a></li>)}</ul></nav>
    <p className={styles.notice}>Demo forms use temporary records. Sample charts and tables below stay separate. Browser comparisons clear when you leave or reload their page; download reports before leaving.</p>
  </section>;
}
