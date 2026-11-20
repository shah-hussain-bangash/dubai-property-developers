'use client';

import { useMemo, useState } from 'react';
import { DataTable, type DataTableColumn } from '@/components/ui/DataTable';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { formatNumber } from '@/lib/format';
import type { PropertyStatus, PropertyUnit } from '@/types/domain';
import styles from './properties.module.css';

const ALL = 'all';

const columns: DataTableColumn<PropertyUnit>[] = [
  {
    key: 'project',
    header: 'Project',
    render: (unit) => (
      <span className="stack-sm" style={{ gap: 2 }}>
        <strong>{unit.project}</strong>
        <span className="subtle">{unit.developer}</span>
      </span>
    ),
  },
  { key: 'community', header: 'Community', render: (unit) => unit.community, hideOnMobile: true },
  { key: 'type', header: 'Type', render: (unit) => unit.unitType },
  { key: 'beds', header: 'Beds', render: (unit) => (unit.bedrooms === 0 ? 'Studio' : unit.bedrooms), align: 'right' },
  { key: 'size', header: 'Size (sq ft)', render: (unit) => formatNumber(unit.sizeSqft), align: 'right', hideOnMobile: true },
  {
    key: 'price',
    header: 'Illustrative price (AED)*',
    render: (unit) => <span title="Illustrative placeholder — not a market price">{formatNumber(unit.illustrativePriceAed)}</span>,
    align: 'right',
  },
  { key: 'status', header: 'Status', render: (unit) => <StatusBadge status={unit.status} size="sm" /> },
  { key: 'handover', header: 'Handover', render: (unit) => unit.handover, hideOnMobile: true },
];

export function PropertiesView({ units }: { units: PropertyUnit[] }) {
  const [query, setQuery] = useState('');
  const [community, setCommunity] = useState<string>(ALL);
  const [bedrooms, setBedrooms] = useState<string>(ALL);
  const [status, setStatus] = useState<PropertyStatus | typeof ALL>(ALL);

  const communities = useMemo(() => Array.from(new Set(units.map((u) => u.community))).sort(), [units]);
  const bedroomOptions = useMemo(
    () => Array.from(new Set(units.map((u) => u.bedrooms))).sort((a, b) => a - b),
    [units],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return units.filter((unit) => {
      if (q && !`${unit.project} ${unit.community} ${unit.developer}`.toLowerCase().includes(q)) return false;
      if (community !== ALL && unit.community !== community) return false;
      if (bedrooms !== ALL && unit.bedrooms !== Number(bedrooms)) return false;
      if (status !== ALL && unit.status !== status) return false;
      return true;
    });
  }, [units, query, community, bedrooms, status]);

  const hasFilters = query !== '' || community !== ALL || bedrooms !== ALL || status !== ALL;

  const resetFilters = () => {
    setQuery('');
    setCommunity(ALL);
    setBedrooms(ALL);
    setStatus(ALL);
  };

  return (
    <section className="panel" aria-labelledby="inventory-title">
      <div className="panel-header">
        <h2 id="inventory-title" className="panel-title">
          Inventory <span className="subtle">({filtered.length} of {units.length})</span>
        </h2>
      </div>

      <form className={styles.filters} role="search" aria-label="Filter properties" onSubmit={(e) => e.preventDefault()}>
        <div className="field">
          <label className="field-label" htmlFor="property-search">
            Search
          </label>
          <input
            id="property-search"
            className="input"
            type="search"
            placeholder="Project, community or developer"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="property-community">
            Community
          </label>
          <select id="property-community" className="select" value={community} onChange={(e) => setCommunity(e.target.value)}>
            <option value={ALL}>All communities</option>
            {communities.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label className="field-label" htmlFor="property-bedrooms">
            Bedrooms
          </label>
          <select id="property-bedrooms" className="select" value={bedrooms} onChange={(e) => setBedrooms(e.target.value)}>
            <option value={ALL}>Any</option>
            {bedroomOptions.map((b) => (
              <option key={b} value={String(b)}>
                {b === 0 ? 'Studio' : `${b} BR`}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label className="field-label" htmlFor="property-status">
            Status
          </label>
          <select
            id="property-status"
            className="select"
            value={status}
            onChange={(e) => setStatus(e.target.value as PropertyStatus | typeof ALL)}
          >
            <option value={ALL}>Any status</option>
            <option value="available">Available</option>
            <option value="reserved">Reserved</option>
            <option value="off_plan">Off-plan</option>
          </select>
        </div>
        <div className={styles.resetCell}>
          <button type="button" className="btn" onClick={resetFilters} disabled={!hasFilters}>
            Reset filters
          </button>
        </div>
      </form>

      <DataTable
        columns={columns}
        rows={filtered}
        getRowKey={(unit) => unit.id}
        caption="Property inventory (fictional demo units)"
        emptyTitle="No units match these filters"
        emptyDescription="Try widening the search or resetting the filters."
      />

      <p className={styles.footnote}>
        * Illustrative placeholder figures for UI layout only. They are not market prices, valuations or offers and
        must not be quoted to clients.
      </p>
    </section>
  );
}
