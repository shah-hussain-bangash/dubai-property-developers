/** Browser-safe types for connected website enquiries and provider bridges. */
export type EnquiryInput={name:string;email:string;phone:string;interest:string;message:string;purpose:string;budgetMax:number;preference:string;permission:string;page:string};
export type EnquiryListing={id:string;reference:string;publicationVersion:number;propertyVersion:number;title:string;askingPrice:number;purpose:string};
export type PortalEnquiry=EnquiryInput&{listing?:EnquiryListing;id:string;reference:string;source:string;sourceLabel:string;assignedTo:string;clientId:string;status:string;notes:string;version:number;createdAt:number;updatedAt:number};
export type EnquiryRecord=PortalEnquiry&{memberId:string;receipt:string};
export type ConnectorRecord={id:string;kind:string;name:string;digest:string;enabled:boolean;createdAt:number;lastReceivedAt:number|null;received:number};
export type ConnectorProfile=Omit<ConnectorRecord,'digest'>;
export const enquiryStatuses=['New','Assigned','In progress','Closed','Spam'];
export const integrationCatalog=[
 {kind:'n8n',name:'n8n workflows',description:'Map approved workflow events into the shared enquiry inbox.',requirement:'An n8n workflow, the intake endpoint and a private bridge key.',url:'https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest/'},
 {kind:'crm',name:'EspoCRM',description:'Receive mapped EspoCRM lead events through an authorised workflow adapter.',requirement:'EspoCRM API or webhook access, signature verification and an adapter that maps each event to one enquiry.',url:'https://docs.espocrm.com/administration/webhooks/'},
 {kind:'whatsapp',name:'WhatsApp Business',description:'Receive enquiry summaries from an authorised WhatsApp workflow. This is not a direct Meta webhook or messaging connection.',requirement:'WhatsApp Business Platform account and a provider/n8n adapter that verifies Meta events before forwarding.',url:'https://whatsappbusiness.com/developers/developer-hub/'},
 {kind:'email',name:'Gmail enquiries',description:'Receive selected email enquiries through your authorised mailbox workflow. This does not sync or send mail.',requirement:'An authorised Gmail OAuth connection in your workflow. Forward only selected enquiry messages.',url:'https://developers.google.com/workspace/gmail/imap/imap-smtp'},
];

export function n8nIntakeStarter(id:string){return {name:'Dubai Property Developers - authorised enquiry intake',active:false,nodes:[{id:'dpd-intake',name:'Save mapped enquiry',type:'n8n-nodes-base.httpRequest',typeVersion:4.2,position:[600,300],parameters:{method:'POST',url:'http://localhost:3000/api/integrations/intake/'+id,authentication:'genericCredentialType',genericAuthType:'httpHeaderAuth',sendBody:true,specifyBody:'json',jsonBody:'={{ { eventId: $json.eventId, lead: $json.lead } }}',options:{}}}],connections:{},settings:{executionOrder:'v1'}};}
