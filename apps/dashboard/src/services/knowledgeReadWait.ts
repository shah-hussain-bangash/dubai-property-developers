export async function waitForKnowledgeRead<T>(signal:AbortSignal,read:()=>Promise<T>):Promise<T>{
 if(signal.aborted)throw Error('Knowledge read cancelled.');
 let rejectInterrupted!:(reason:Error)=>void;
 const interrupted=new Promise<never>((_resolve,reject)=>{rejectInterrupted=reject;});
 const onAbort=()=>rejectInterrupted(Error('Knowledge read cancelled.'));
 signal.addEventListener('abort',onAbort,{once:true});
 try{
  let pending:Promise<T>;
  try{pending=read();}catch(error){pending=Promise.reject(error);}
  return await Promise.race([pending,interrupted]);
 }finally{signal.removeEventListener('abort',onAbort);}
}
