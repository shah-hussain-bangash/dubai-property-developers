export type ReviewEvent={event_id:string;reviewed_at:string;reviewed_by:string;previous_review_by:string|null;review_by:string;previous_customer_safe:boolean;customer_safe:boolean};
export type SourceReviewHistory={agent_id:string;source_id:string;events:ReviewEvent[];has_more:boolean;next_cursor:string|null};
function calendarDate(value:unknown):boolean{
 if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
 const date=new Date(value+'T00:00:00Z');return Number.isFinite(date.getTime())&&date.toISOString().slice(0,10)===value;
}
export function parseSourceReviewHistory(value:SourceReviewHistory,agent:string,sourceId:string):SourceReviewHistory{
 const invalid=()=>Error('The source review history could not be verified.');
 if(!value||value.agent_id!==agent||value.source_id!==sourceId||!Array.isArray(value.events)||value.events.length>20||typeof value.has_more!=='boolean'||(value.has_more&&value.events.length!==20))throw invalid();
 const ids=new Set<string>();
 for(const e of value.events){
  if(!e||typeof e.event_id!=='string'||!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(e.event_id)||ids.has(e.event_id)||typeof e.reviewed_by!=='string'||!e.reviewed_by.trim()||e.reviewed_by.length>500||/[\x00-\x1f\x7f]/.test(e.reviewed_by)||typeof e.reviewed_at!=='string'||!/^\d{4}-\d{2}-\d{2}T[\d:.]+(?:Z|\+00:00)$/.test(e.reviewed_at)||!Number.isFinite(Date.parse(e.reviewed_at))||!calendarDate(e.review_by)||(e.previous_review_by!==null&&!calendarDate(e.previous_review_by))||typeof e.customer_safe!=='boolean'||typeof e.previous_customer_safe!=='boolean')throw invalid();
  ids.add(e.event_id);
 }
 if(value.next_cursor!==(value.has_more?value.events[value.events.length-1].event_id:null))throw invalid();
 return value;
}
