// Trusted operator only. Sentinel account routes to instrumented tap; originals remain in tap.
import { readFile, writeFile } from 'node:fs/promises';
const jwt=(await readFile('/operator/admin-token','utf8')).trim();
async function api(path,body,token=jwt){const r=await fetch('http://sub2api:8080/api/v1'+path,{method:body===undefined?'GET':'POST',headers:{authorization:`Bearer ${token}`,'content-type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});if(!r.ok)throw Error('Private setup HTTP'+r.status);return(await r.json()).data;}
const cfg=JSON.parse(await readFile('/operator/tap-private/tap.json','utf8'));
const g=await api('/admin/groups',{name:'rr-sub2-diag-20261001-exclusive',platform:'openai',is_exclusive:true,subscription_type:'standard',rate_multiplier:1,fallback_group_id:null,fallback_group_id_on_invalid_request:null});
const a=await api('/admin/accounts',{name:'rr-sub2-diag-20261001-mimo',platform:'openai',type:'apikey',concurrency:2,priority:1,group_ids:[g.id],upstream_billing_probe_enabled:false,credentials:{api_key:cfg.sentinel,base_url:'http://tap:8790/v1',model_mapping:{'mimo-v2.6-pro':'mimo-v2.6-pro'}},extra:{openai_responses_mode:'force_responses',openai_passthrough:true}});
const u=await api('/admin/users',{email:'diag@rr-sub2-spike.invalid',password:cfg.userPassword,username:'rr-sub2-diag',role:'user',balance:1000,concurrency:2,allowed_groups:[g.id],restrict_public_groups:true});
const auth=await api('/auth/login',{email:u.email,password:cfg.userPassword});
const key=await api('/keys',{name:'rr-sub2-diag-20261001',group_id:g.id,expires_in_days:1},auth.access_token);
cfg.engineKey=key.key;delete cfg.userPassword;
await writeFile('/operator/tap-private/tap.json',JSON.stringify(cfg),{mode:0o600});
await writeFile('/operator/setup-metadata.json',JSON.stringify({groupID:g.id,accountID:a.id,userID:u.id,keyID:key.id}),{mode:0o600});
// Create probe was rejected by tap while disabled, no real inference from setup.
await new Promise(r=>setTimeout(r,1000));
for(const p of ['clear-error','recover-state','clear-rate-limit'])await api(`/admin/accounts/${a.id}/${p}`,{});
await api(`/admin/accounts/${a.id}/schedulable`,{schedulable:true});
console.log(JSON.stringify({setup:true,group:g.id,account:a.id,real_provider_key_loaded_into_engine:false,live_probe_enabled:false}));
