'use client';
export type FalField = {type:string; title?:string; description?:string; enum?:string[]; default?:string|number|boolean; minimum?:number; maximum?:number};
export default function FalFields({fields,value,onChange,t}:{fields:Record<string,FalField>;value:Record<string,string|number|boolean>;onChange:(next:Record<string,string|number|boolean>)=>void;t:(key:string)=>string}) {
 return <div className="field-row fal-fields">{Object.entries(fields).map(([name,field])=>{
  const label = name==='voice' ? t('chooseVoice') : name==='speed' ? t('falVoiceSpeed') : field.title || name;
  const current = value[name] ?? field.default ?? '';
  return <label key={name}>{label}{field.enum ? <select aria-label={label} value={String(current)} onChange={e=>onChange({...value,[name]:e.target.value})}>{field.enum.map(option=><option key={option} value={option}>{option.startsWith('am_') ? t('maleVoiceLabel')+' · '+option.slice(3) : option.startsWith('af_') ? t('femaleVoiceLabel')+' · '+option.slice(3) : option}</option>)}</select> : field.type==='boolean' ? <input aria-label={label} type="checkbox" checked={Boolean(current)} onChange={e=>onChange({...value,[name]:e.target.checked})}/> : <input aria-label={label} type={field.type==='number'||field.type==='integer'?'number':'text'} min={field.minimum} max={field.maximum} step={field.type==='integer'?1:0.1} value={String(current)} onChange={e=>onChange({...value,[name]:field.type==='string'?e.target.value:Number(e.target.value)})}/>}</label>;
 })}</div>;
}
