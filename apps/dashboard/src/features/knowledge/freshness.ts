import { daysBetween } from '@/lib/format';
import type { KnowledgeDocument } from '@/types/domain';

export interface KnowledgeRow extends KnowledgeDocument {
  ageDays: number;
  stale: boolean;
}

/** A document is stale once its age exceeds its review interval. */
export function getFreshness(doc: KnowledgeDocument, nowIso: string): KnowledgeRow {
  const ageDays = Math.max(0, daysBetween(doc.updatedAt, nowIso));
  return { ...doc, ageDays, stale: ageDays > doc.reviewIntervalDays };
}
