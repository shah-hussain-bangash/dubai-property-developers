import { humanize } from '@/lib/format';
import styles from './workflows.module.css';

export interface WorkflowPipelineProps {
  steps: string[];
  label: string;
}

/** Ordered step pipeline; wraps to multiple rows on narrow screens. */
export function WorkflowPipeline({ steps, label }: WorkflowPipelineProps) {
  if (steps.length === 0) {
    return <p className="subtle">No steps defined.</p>;
  }
  return (
    <ol className={styles.pipeline} aria-label={label}>
      {steps.map((step, index) => (
        <li key={`${step}-${index}`} className={styles.step}>
          <span className={styles.stepIndex} aria-hidden="true">
            {index + 1}
          </span>
          <span className={styles.stepBody}>
            <span className={styles.stepName}>{humanize(step)}</span>
            <code className={styles.stepId}>{step}</code>
          </span>
          {index < steps.length - 1 ? (
            <span className={styles.connector} aria-hidden="true">
              <svg viewBox="0 0 24 12" width="24" height="12" fill="none" stroke="currentColor" strokeWidth="1.6">
                <path d="M1 6h20M16 1.5 21 6l-5 4.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
          ) : null}
        </li>
      ))}
    </ol>
  );
}
