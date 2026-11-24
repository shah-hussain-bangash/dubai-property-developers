import type {Metadata} from 'next';
import {PageHeader} from '@/components/ui/PageHeader';
import {AgentKnowledgePanel} from '@/features/knowledge/AgentKnowledgePanel';
export const metadata:Metadata={title:'Agent knowledge'};
export default function KnowledgePage(){return <><PageHeader eyebrow="AGENT WORKSPACE" title="Agent knowledge" description="Give each agent its own sources. Upload documents, import a website page or paste approved text, then check a cited answer."/><AgentKnowledgePanel/></>;}
