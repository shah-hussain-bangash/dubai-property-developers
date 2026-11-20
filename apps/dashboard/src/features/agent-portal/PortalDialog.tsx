'use client';
import {useEffect,useRef,type ReactNode} from 'react';
import s from './AgentPortal.module.css';
export function PortalDialog({label,onClose,locked=false,children}:{label:string;onClose:()=>void;locked?:boolean;children:ReactNode}){
 const ref=useRef<HTMLElement>(null);const close=useRef(onClose);const blocking=useRef(locked);close.current=onClose;blocking.current=locked;
 useEffect(()=>{const previous=document.activeElement;const oldOverflow=document.body.style.overflow;document.body.style.overflow='hidden';
 const focusables=()=>Array.from(ref.current?.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]')||[]).filter(el=>el.getClientRects().length>0);
 (focusables()[0]||ref.current)?.focus();
 function key(e:KeyboardEvent){if(e.key==='Escape'){e.preventDefault();if(!blocking.current)close.current();}if(e.key==='Tab'){const list=focusables();if(!list.length){e.preventDefault();ref.current?.focus();return;}const first=list[0],last=list[list.length-1];if(e.shiftKey&&(document.activeElement===first||!ref.current?.contains(document.activeElement))){e.preventDefault();last.focus();}else if(!e.shiftKey&&(document.activeElement===last||!ref.current?.contains(document.activeElement))){e.preventDefault();first.focus();}}}
 document.addEventListener('keydown',key);return()=>{document.removeEventListener('keydown',key);document.body.style.overflow=oldOverflow;if(previous instanceof HTMLElement&&previous.isConnected)previous.focus();};},[]);
 return <div className={s.modal}><section ref={ref} className={s.modalCard} role="dialog" aria-modal="true" aria-label={label} tabIndex={-1}>{children}</section></div>;
}
