'use client';
import {useState,type FormEvent} from 'react';
import type {AssignedSource} from '@/services/agentKnowledge';
import s from './AgentKnowledgePanel.module.css';

export function SourceReviewForm({source,disabled,onReview}:{source:AssignedSource;disabled:boolean;onReview:(date:string,customerSafe:boolean)=>Promise<void>}){
 const [date,setDate]=useState(source.review_by??''),[reviewed,setReviewed]=useState(false),[customerSafe,setCustomerSafe]=useState(false);
 async function save(event:FormEvent){event.preventDefault();if(!reviewed||!date)return;await onReview(date,customerSafe);}
 return <form className={s.box} onSubmit={save}><h4>Record a source review</h4><p>After checking the saved text above, choose its next review date. Saving makes this source staff-only unless you explicitly approve customer use below. The saved text and owner stay the same. Customer approval is available after you confirm review; changing the date or withdrawing that confirmation clears the draft approval.</p><fieldset disabled={disabled}><label htmlFor="renew-review-date">Next review date</label><input id="renew-review-date" type="date" required max="9999-12-31" value={date} onChange={e=>{setDate(e.target.value);setReviewed(false);setCustomerSafe(false);}}/><label className={s.checkbox}><input type="checkbox" required checked={reviewed} onChange={e=>{setReviewed(e.target.checked);setCustomerSafe(false);}}/> I have reviewed this saved source</label><label className={s.checkbox}><input type="checkbox" disabled={!reviewed||!date} checked={customerSafe} onChange={e=>setCustomerSafe(e.target.checked)}/> Approve this reviewed source for customer answers</label><button className="btn btn-primary" type="submit" disabled={!reviewed||!date}>Save source review</button></fieldset></form>;
}
