import type { Metadata } from 'next';
import { DemoDataBanner } from '@/components/ui/DemoDataBanner';
import { PageHeader } from '@/components/ui/PageHeader';
import { LocalAiPanel } from '@/features/conversations/LocalAiPanel';
import { DemoReplyForm } from '@/features/conversations/DemoReplyForm';
import { ConversationsView } from '@/features/conversations/ConversationsView';
import { DEMO_CONVERSATIONS } from '@/lib/demo-data';

export const metadata: Metadata = {
  title: 'Conversations',
};

export default function ConversationsPage() {
  const escalated = DEMO_CONVERSATIONS.filter((c) => c.escalated).length;
  return (
    <>
      <PageHeader
        eyebrow="Operations"
        title="Conversations"
        description={`Lead conversations across WhatsApp, email and web chat. ${escalated} flagged for human follow-up.`}
      />
      <DemoDataBanner>Conversations and participants are fictional; no messages were sent.</DemoDataBanner>
      <LocalAiPanel />
      <DemoReplyForm />
      <ConversationsView conversations={DEMO_CONVERSATIONS} />
    </>
  );
}
