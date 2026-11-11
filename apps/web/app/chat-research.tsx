'use client';
import {useEffect,useRef,useState} from 'react';
import type {Element} from 'hast';
import ChatCopyButton from './chat-copy';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {Globe,ExternalLink,X,ChevronRight} from 'lucide-react';

function blockText(node: Element): string {
  return node.children.map(child => child.type === 'text' ? child.value : child.type === 'element' ? blockText(child) : '').join('');
}
function CopyableBlock({node,t}:{node?:Element;t:(key:string)=>string}) {
  if (!node) return null;
  const code = node.children.find(child => child.type === 'element' && child.tagName === 'code') as Element | undefined;
  // The parser adds one terminal newline to a fenced block; preserve all original content otherwise.
  const text = blockText(code || node).replace(/\n$/, '');
  const classes = code?.properties?.className;
  const language = (Array.isArray(classes) ? classes.join(' ') : String(classes || '')).match(/language-([^ ]+)/)?.[1] || '';
  const after = language === 'copy-after';
  const purpose = ['copy','copy-before','copy-after','text','plaintext'].includes(language) ? '' : language;
  const control = <div className="chat-copy-block-bar">{purpose && <span>{purpose}</span>}<ChatCopyButton text={text} t={t} label={t('chatCopyBlock')}/></div>;
  return <div className={'chat-copy-block' + (!purpose ? ' prose-block' : '') + (after ? ' copy-after' : '')}>
    {!after && control}<pre><code className={purpose ? 'language-'+purpose : undefined}>{text}</code></pre>{after && control}
  </div>;
}
export type Research={sources:{url:string;title:string}[];queries?:string[];search_html?:string};
export function ChatResponse({reply,research,t}:{reply:string;research?:Research;t:(key:string)=>string}){
  const [open,setOpen]=useState(false),[selected,setSelected]=useState<number|null>(null);
  const dialog=useRef<HTMLDialogElement>(null);
  const cards=useRef<(HTMLAnchorElement|null)[]>([]);
  const show=(index:number|null=null)=>{setSelected(index);setOpen(true);};
  useEffect(()=>{if(open){dialog.current?.showModal();if(selected!==null)cards.current[selected]?.scrollIntoView({block:'nearest'});}else dialog.current?.close();},[open,selected]);
  const sources=research?.sources||[];
  const body=reply.split(/(```[\s\S]*?```|`[^`\n]*`)/g).map(part=>part.startsWith('`')?part:part.replace(/\[(\d+(?:,\s*\d+)*)\]/g,(original,ids:string)=>{
    const numbers=ids.split(',').map(value=>Number(value.trim()));
    return numbers.every(number=>number>0&&number<=sources.length)?numbers.map(number=>`[${number}](#haytile-source-${number})`).join(''):original;
  })).join('');
  return <>
    <div className="chat-response chat-markdown"><Markdown remarkPlugins={[remarkGfm]} components={{pre:({node})=><CopyableBlock node={node} t={t}/>,a:({href,children})=>{
      const match=href?.match(/^#haytile-source-(\d+)$/);
      if(match)return <button type="button" className="chat-citation" aria-label={t('chatSources')+' '+match[1]} onClick={()=>show(Number(match[1])-1)}>{children}</button>;
      return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
    }}}>{body}</Markdown></div>
    {research&&<div className="chat-research-summary"><button type="button" className="chat-source-trigger" onClick={()=>show()}><Globe size={15}/>{t('chatSources')} · {sources.length}<ChevronRight size={14}/></button>{!sources.length&&<small>{t('chatNoWebSources')}</small>}{research.search_html&&<iframe className="chat-search-suggestions" title={t('chatSearchSuggestions')} sandbox="allow-popups allow-popups-to-escape-sandbox" referrerPolicy="no-referrer" srcDoc={'<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src https: data:; base-uri \'none\'; form-action \'none\'">'+research.search_html}/>}</div>}
    <dialog ref={dialog} className="chat-research-dialog" onCancel={()=>setOpen(false)} onClick={event=>{if(event.target===dialog.current)setOpen(false);}}><header><h2>{t('chatSources')}</h2><button type="button" onClick={()=>setOpen(false)} aria-label={t('chatCloseSources')}><X size={20}/></button></header><div className="chat-research-cards">{sources.map((source,index)=><a key={source.url} ref={node=>{cards.current[index]=node;}} href={source.url} target="_blank" rel="noopener noreferrer" className={selected===index?'selected':''}><span>{index+1} · {new URL(source.url).hostname}</span><strong>{source.title}</strong><ExternalLink size={14}/></a>)}{research?.queries?.length?<details><summary>{t('chatResearchQueries')}</summary>{research.queries.map((query,index)=><p key={index}>{query}</p>)}</details>:null}</div></dialog>
  </>;
}
