
'use client';
import Link from 'next/link';
import {useRef,useState} from 'react';
import {Brand} from './Brand';
import s from './Portal.module.css';
export function WebsiteHeader({page='home'}:{page?:'home'|'offers'|'enquire'|'catalogue'}){
 const [open,setOpen]=useState(false);const toggle=useRef<HTMLButtonElement>(null);
 const section=(id:string)=>(page==='home'?'':'/')+'#'+id;
 return <header className={s.siteHeader} onKeyDown={e=>{if(e.key==='Escape'&&open){setOpen(false);toggle.current?.focus();}}}>
  <div className={s.headerTop}><Brand/><div className={s.headerPromise}><span/>DUBAI AMBITION. CONNECTED.</div><div className={s.headerActions}><Link href="/login" className={s.agentSignIn}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><circle cx="12" cy="8" r="3.5"/><path d="M5 21v-2a7 7 0 0114 0v2"/></svg>Agent sign in</Link><Link href="/signup" className={s.joinNetwork}>Join our network <span aria-hidden="true">↗</span></Link></div><button ref={toggle} className={s.websiteMenuToggle} aria-label="Toggle navigation" aria-expanded={open} aria-controls="public-website-menu" onClick={()=>setOpen(!open)}><span aria-hidden="true">{open?'×':'☰'}</span><span>Menu</span></button></div>
  <nav id="public-website-menu" aria-label="Website navigation" className={s.websiteNav+' '+(open?s.websiteNavOpen:'')} onClick={e=>{if((e.target as HTMLElement).closest('a'))setOpen(false);}}><div><Link href={page==='home'?'#home':'/'} className={page==='home'?s.currentPage:''} aria-current={page==='home'?'page':undefined}>Home</Link><Link href="/catalogue" className={page==='catalogue'?s.currentPage:''} aria-current={page==='catalogue'?'page':undefined}>Properties</Link><Link href={section('collaboration')}>Developer collaboration</Link><Link href="/current-offers" className={page==='offers'?s.currentPage:''} aria-current={page==='offers'?'page':undefined}>Current opportunities</Link><Link href={section('how-it-works')}>How it works</Link><Link href={section('about')}>About us</Link><Link href="/enquire" className={page==='enquire'?s.currentPage:''} aria-current={page==='enquire'?'page':undefined}>Enquire</Link></div></nav>
 </header>;
}
