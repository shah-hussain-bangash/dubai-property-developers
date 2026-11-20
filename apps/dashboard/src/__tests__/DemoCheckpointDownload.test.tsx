import { render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DemoQuickStart } from '@/features/overview/DemoQuickStart';
afterEach(()=>{vi.unstubAllGlobals();vi.restoreAllMocks();});
describe('demo verification summary download',()=>{
 it('links to a fixed local snapshot with an explicit download filename',()=>{render(<DemoQuickStart/>);expect(screen.getByRole('link',{name:'Download verification summary'})).toHaveAttribute('href','/local-demo-checkpoint-step607.txt');expect(screen.getByRole('link',{name:'Download verification summary'})).toHaveAttribute('download','dubai-real-estate-ai-checkpoint-step607.txt');expect(screen.getByText(/Step 607 evidence snapshot; this download does not check current service availability or live readiness./)).toBeVisible();});
 it('keeps the guide and all five direct demo links',()=>{render(<DemoQuickStart/>);expect(screen.getByRole('link',{name:'Download demo guide'})).toHaveAttribute('href','/local-demo-user-guide.txt');expect(within(screen.getByRole('navigation',{name:'Interactive fictional demos'})).getAllByRole('link')).toHaveLength(5);});
 it('makes no automatic requests or credential controls',()=>{const f=vi.fn();vi.stubGlobal('fetch',f);const {container}=render(<DemoQuickStart/>);expect(f).not.toHaveBeenCalled();expect(container.querySelector('form,input,textarea,button')).toBeNull();expect(screen.getByText(/Mock services send no live messages or bookings/)).toBeVisible();});
});
