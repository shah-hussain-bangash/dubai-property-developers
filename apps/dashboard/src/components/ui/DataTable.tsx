import type { ReactNode } from 'react';
import { cx } from '@/lib/cx';
import { EmptyState } from './EmptyState';
import styles from './DataTable.module.css';

export interface DataTableColumn<T> {
  /** Stable column key (used as React key). */
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  align?: 'left' | 'right' | 'center';
  /** Hide the column on narrow screens. */
  hideOnMobile?: boolean;
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  rows: T[];
  getRowKey: (row: T) => string;
  /** Accessible table caption (visually hidden unless `showCaption`). */
  caption: string;
  showCaption?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
}

/**
 * Generic typed table. Deliberately not a client component so server pages
 * can pass render functions directly.
 */
export function DataTable<T>({
  columns,
  rows,
  getRowKey,
  caption,
  showCaption = false,
  emptyTitle = 'No records',
  emptyDescription,
}: DataTableProps<T>) {
  if (rows.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} compact />;
  }

  return (
    <div className={styles.scroller} role="region" aria-label={caption} tabIndex={0}>
      <table className={styles.table}>
        <caption className={showCaption ? styles.caption : 'visually-hidden'}>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={cx(
                  column.align === 'right' && styles.right,
                  column.align === 'center' && styles.center,
                  column.hideOnMobile && styles.hideOnMobile,
                )}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={getRowKey(row)}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={cx(
                    column.align === 'right' && styles.right,
                    column.align === 'center' && styles.center,
                    column.hideOnMobile && styles.hideOnMobile,
                  )}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
