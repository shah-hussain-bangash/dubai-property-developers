'use client';

import { useState } from 'react';
import { EmptyState } from '@/components/ui/EmptyState';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { cx } from '@/lib/cx';
import { formatDateTime, formatTime } from '@/lib/format';
import type { Conversation, ConversationChannel } from '@/types/domain';
import styles from './conversations.module.css';

const CHANNEL_LABELS: Record<ConversationChannel, string> = {
  whatsapp: 'WhatsApp',
  email: 'Email',
  web: 'Web chat',
};

const SENDER_LABELS = {
  lead: 'Lead',
  agent: 'AI agent',
  human: 'Human',
} as const;

export function ConversationsView({ conversations }: { conversations: Conversation[] }) {
  const [selectedId, setSelectedId] = useState<string | null>(conversations[0]?.id ?? null);
  const selected = conversations.find((c) => c.id === selectedId) ?? null;

  if (conversations.length === 0) {
    return <EmptyState title="No conversations" description="Conversations from WhatsApp, email and web chat will appear here." />;
  }

  return (
    <div className={styles.layout}>
      <section className={cx('panel', styles.listPanel)} aria-labelledby="conversation-list-title">
        <h2 id="conversation-list-title" className="panel-title">
          Inbox <span className="subtle">({conversations.length})</span>
        </h2>
        <ul className={styles.list}>
          {conversations.map((conversation) => {
            const isSelected = conversation.id === selectedId;
            return (
              <li key={conversation.id}>
                <button
                  type="button"
                  className={cx(styles.item, isSelected && styles.itemSelected)}
                  aria-pressed={isSelected}
                  onClick={() => setSelectedId(conversation.id)}
                >
                  <span className={styles.itemTop}>
                    <strong>{conversation.leadName}</strong>
                    <span className="subtle">{formatTime(conversation.lastMessageAt)}</span>
                  </span>
                  <span className={styles.itemSubject}>{conversation.subject}</span>
                  <span className={styles.itemMeta}>
                    <span className="chip">{CHANNEL_LABELS[conversation.channel]}</span>
                    {conversation.escalated ? <StatusBadge status="escalated" tone="danger" label="Escalated" size="sm" /> : null}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </section>

      <section className={cx('panel', styles.threadPanel)} aria-labelledby="thread-title" aria-live="polite">
        {selected ? (
          <>
            <header className={styles.threadHeader}>
              <div>
                <h2 id="thread-title" className="panel-title">
                  {selected.subject}
                </h2>
                <p className="panel-subtitle">
                  {selected.leadName} · {CHANNEL_LABELS[selected.channel]} · handled by {selected.handledBy}
                </p>
              </div>
              {selected.escalated ? (
                <StatusBadge status="escalated" tone="danger" label="Needs human" />
              ) : (
                <StatusBadge status="automated" tone="success" label="Automated" />
              )}
            </header>

            {selected.escalated && selected.escalationReason ? (
              <div className={styles.escalation} role="note">
                <strong>Escalation:</strong> {selected.escalationReason}
              </div>
            ) : null}

            <ol className={styles.thread} aria-label="Messages">
              {selected.messages.map((message) => (
                <li key={message.id} className={cx(styles.message, styles[message.sender])}>
                  <span className={styles.messageMeta}>
                    <strong>{message.author}</strong>
                    <span className="subtle">
                      {SENDER_LABELS[message.sender]} · {formatDateTime(message.sentAt)}
                    </span>
                  </span>
                  <p className={styles.messageText}>{message.text}</p>
                </li>
              ))}
            </ol>

            <p className={styles.composerNote}>
              Replying from the dashboard is not available yet. Agent drafts require human approval before sending.
            </p>
          </>
        ) : (
          <>
            <h2 id="thread-title" className="visually-hidden">
              Conversation thread
            </h2>
            <EmptyState title="Select a conversation" compact />
          </>
        )}
      </section>
    </div>
  );
}
