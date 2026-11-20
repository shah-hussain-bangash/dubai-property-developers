/** Browser-safe publication types. Public DTOs exclude private owner/review fields. */
export type PublicFields={title:string;location:string;type:string;purpose:string;price:number;beds:number;baths:number;area:number;description:string};
export type Publication=PublicFields&{propertyId:string;agentId:string;reference:string;version:number;sourceVersion:number;state:'requested'|'published'|'rejected'|'withdrawn';photoIds:string[];submittedAt:number;updatedAt:number;publishedAt:number|null;reviewNote:string};
export type PublicListing=PublicFields&{id:string;reference:string;version:number;sourceVersion:number;photoIds:string[];publishedAt:number;updatedAt:number};
