'use client';
import Link from 'next/link';
import {useRef,useState,type FormEvent} from 'react';
import styles from './LoginForm.module.css';
export function LoginForm({portal='auto'}:{portal?:'auto'|'admin'|'agent'}){
 const [email,setEmail]=useState('');const [password,setPassword]=useState('');const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [visible,setVisible]=useState(false);const active=useRef(false);
 async function signIn(event:FormEvent){event.preventDefault();if(active.current)return;active.current=true;setBusy(true);setError('');
 try{const response=await fetch('/api/portal-auth/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password,...(portal==='auto'?{}:{portal})}),redirect:'error',cache:'no-store'});
 if(response.ok){const result=await response.json();setPassword('');window.location.assign(result.destination==='/account'?'/account':result.destination==='/agent-portal'?'/agent-portal':'/overview');return;}
 const value=await response.json().catch(()=>({}));setError(typeof value.error==='string'?value.error:'Sign-in failed. Please try again.');
 }catch{setError('We could not reach your workspace. Please try again.');}finally{active.current=false;setBusy(false);}}
 return <form className={styles.form} onSubmit={signIn}><label htmlFor="login-email">Email address</label><input id="login-email" name="email" required type="email" maxLength={254} autoComplete="username" placeholder="you@company.com" value={email} onChange={e=>setEmail(e.target.value)} disabled={busy}/>
 <label htmlFor="login-password">Password</label><div className={styles.password}><input id="login-password" name="password" required type={visible?'text':'password'} maxLength={128} autoComplete="current-password" placeholder="Enter your password" value={password} onChange={e=>setPassword(e.target.value)} disabled={busy}/><button type="button" aria-label={visible?'Hide password':'Show password'} onClick={()=>setVisible(!visible)}>{visible?'Hide':'Show'}</button></div>
 {error&&<p role="alert" className={styles.error}>{error}</p>}<button className={styles.submit} disabled={busy} type="submit">{busy?'Signing in…':portal==='admin'?'Sign in as Admin':portal==='agent'?'Sign in to Agent Portal':'Sign in to your workspace'} <span aria-hidden="true">↗</span></button><p className={styles.help}>{portal==='admin'?'Agent or member? ': 'New to Dubai Property Developers? '} <Link href={portal==='admin'?'/login':'/agent-signup'}>{portal==='admin'?'Go to Agent sign-in':'Create an agent account'}</Link></p>{portal!=='admin'&&<p className={styles.help}><Link href="/forgot-password">Forgot your password?</Link></p>}<p className={styles.session}>Your session stays signed in for up to 8 hours.</p></form>;
}
