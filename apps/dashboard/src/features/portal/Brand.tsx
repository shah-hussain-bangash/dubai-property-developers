import Link from 'next/link';
import styles from './Portal.module.css';
export function Brand(){return <Link href="/" className={styles.brand} aria-label="Dubai Property Developers home"><img src="/images/developers/dubai-property-developers-logo.png" alt=""/><span>DUBAI PROPERTY<strong>DEVELOPERS</strong><small>INVEST · BUILD · GROW TOGETHER</small></span></Link>;}
