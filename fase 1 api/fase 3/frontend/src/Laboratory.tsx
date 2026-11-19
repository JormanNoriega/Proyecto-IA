import { useCallback, useEffect, useState } from "react";
import { Activity, Check, Database, FlaskConical, Play, RefreshCw } from "lucide-react";

type Version = {id:number; created:string; records:number; checksum:string; operational_count:number};
type Operational = {id:number; code:string; year:number; source:string; data_sha256:string; data:Record<string,string|number|null>};
type TrainingChoice = {label:string; label_source:string};
type Score = {accuracy:number; precision:number; recall:number; f1:number; roc_auc:number|null; pr_auc:number|null; rows:number; matrix:number[][]};
type Experiment = {id:number; dataset_id:number; status:string; created:string; info:{selected?:string; warning?:string; error?:string; split?:Record<string,{records:number;municipalities:number}>; validation?:Record<string,Score>; test?:Score|null}};
type Props = {request:(path:string, options?:RequestInit)=>Promise<any>; json:(body:unknown)=>RequestInit; onPublished:()=>void};
const show = (v:number|null|undefined) => v == null ? "—" : (v*100).toFixed(1)+"%";

function Metrics({name, score}:{name:string;score:Score}) {
  return <div className="metric-block"><div className="metric-title"><strong>{name}</strong><span>{score.rows} registros</span></div><div className="metric-grid"><div><span>Precisión</span><strong>{show(score.precision)}</strong></div><div><span>Recall</span><strong>{show(score.recall)}</strong></div><div><span>F1</span><strong>{show(score.f1)}</strong></div><div><span>ROC-AUC</span><strong>{show(score.roc_auc)}</strong></div><div><span>PR-AUC</span><strong>{show(score.pr_auc)}</strong></div></div><p className="footnote">Matriz de confusión · VN {score.matrix[0][0]} · FP {score.matrix[0][1]} · FN {score.matrix[1][0]} · VP {score.matrix[1][1]}</p></div>
}

export default function Laboratory({request,json,onPublished}:Props) {
  const [versions,setVersions]=useState<Version[]>([]);
  const [experiments,setExperiments]=useState<Experiment[]>([]);
  const [version,setVersion]=useState("");
  const [active,setActive]=useState<number|null>(null);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const [busy,setBusy]=useState(false);
  const [records,setRecords]=useState<Operational[]>([]);
  const [features,setFeatures]=useState<string[]>([]);
  const [choices,setChoices]=useState<Record<number,TrainingChoice>>({});
  const load=useCallback(async()=>{
    try {
      const [v,e,a]=await Promise.all([request("/dataset-versions"),request("/experiments"),request("/models/active")]);
      setVersions(v);setExperiments(e);setActive(a.id);
      setVersion(current=>current || (v[0]?.id ? String(v[0].id) : ""));
    } catch(e) {setError((e as Error).message)}
  },[request]);
  useEffect(()=>{load();const timer=window.setInterval(load,3000);return()=>window.clearInterval(timer)},[load]);
  async function loadRecords() {
    try {const [r,s]=await Promise.all([request("/data/records"),request("/data/schema")]);setRecords(r);setFeatures(s.features);setChoices({});setError("")}
    catch(e){setError((e as Error).message)}
  }
  useEffect(()=>{loadRecords()},[]);
  async function act(action:()=>Promise<any>, success:string) {
    setBusy(true);setError("");setMessage("");
    try {await action();await load();setMessage(success)} catch(e) {setError((e as Error).message)} finally {setBusy(false)}
  }
  const running=experiments.some(e=>e.status==="pendiente"||e.status==="ejecutando");
  const completeRecords=records.filter(r=>features.length===27&&features.every(f=>r.data[f]!=null)&&r.data.consultas!=null);
  return <>
    <div className="heading-row"><div><div className="overline"><span/> LABORATORIO DE INTELIGENCIA ARTIFICIAL</div><h1>Del dato a la decisión.</h1><p>Crea una versión, entrena y evalúa antes de publicar un modelo.</p></div><button className="secondary" onClick={load}><RefreshCw size={15}/> Actualizar</button></div>
    {error&&<div className="alert" role="alert">{error}</div>}{message&&<div className="success" role="status"><Check size={16}/>{message}</div>}
    <div className="info-box"><Activity size={18}/><p><strong>Importante:</strong> las etiquetas históricas se construyeron antes de separar municipios. Las métricas pueden contener contaminación; no representan una prueba ciega rigurosa. Los datos sin etiqueta o características suficientes no se usan para entrenar.</p></div>
    <div className="two-cols lab-actions">
      <section className="panel"><div className="panel-title"><Database/><div><h2>1. Congelar dataset</h2><p>Incluye el histórico, los registros adicionales anteriores y los operativos seleccionados abajo. Crear la versión no cambia el modelo activo.</p></div></div><button className="secondary full" disabled={busy} onClick={()=>act(()=>request("/dataset-versions",json({operational_inputs:records.filter(r=>choices[r.id]).map(r=>({record_id:r.id,data_sha256:r.data_sha256}))})),"Versión creada con la selección indicada.")}>Crear versión del dataset · {Object.keys(choices).length} operativos</button><div className="version-list">{versions.map(v=><div key={v.id}><span><strong>Versión #{v.id}</strong><small>{v.records.toLocaleString("es-CO")} registros · {v.operational_count} operativos seleccionados · {new Date(v.created).toLocaleString("es-CO")}</small></span><code>{v.checksum.slice(0,10)}</code></div>)}{!versions.length&&<p className="footnote">Aún no existen versiones guardadas.</p>}</div></section>
      <section className="panel"><div className="panel-title"><FlaskConical/><div><h2>2. Entrenar candidatos</h2><p>Separación 70/15/15 por municipio y comparación en validación.</p></div></div><label className="lab-label">Versión del dataset<select value={version} onChange={e=>setVersion(e.target.value)}><option value="">Selecciona una versión</option>{versions.map(v=><option key={v.id} value={v.id}>Versión #{v.id} · {v.records} registros</option>)}</select></label><button className="primary full" disabled={!version||running||busy} onClick={()=>act(()=>request("/experiments",json({dataset_id:Number(version)})),"Entrenamiento iniciado. La página se actualiza automáticamente.")}><Play size={16}/>{running?"Entrenamiento en curso…":"Entrenar modelo"}</button><p className="footnote">Se comparan un clasificador HistGradientBoosting y una referencia básica; los faltantes se imputan usando solo entrenamiento.</p></section>
    </div>
    <section className="panel data-preview"><div className="panel-title"><div><h2>Seleccionar registros operativos para entrenar</h2><p>Opcional. Selecciona registros completos con consultas; la prioridad se calcula automáticamente al crear la versión.</p></div></div>
      <p className="footnote">El entrenamiento actual excluye municipios identificados como hub. Si la clasificación histórica indica hub o no es inequívoca, la versión no se creará. Se muestran los últimos 500 registros; actualizar la lista borra la selección actual.</p>
      <button className="primary" type="button" onClick={loadRecords}>Actualizar registros</button>
      <button className="secondary" type="button" disabled={!completeRecords.length} onClick={()=>setChoices(current=>{const next={...current};completeRecords.forEach(r=>{if(!next[r.id])next[r.id]={label:"",label_source:""}});return next})}>Seleccionar todos los completos ({completeRecords.length})</button>
      <button className="secondary" type="button" disabled={!Object.keys(choices).length} onClick={()=>setChoices({})}>Deseleccionar todos</button>
      <p className="footnote">La selección masiva incluye únicamente los registros mostrados con los 27 predictores. Debes indicar la etiqueta y su origen para cada uno; la clasificación como hub se comprueba al crear la versión.</p>
      {records.length?<div className="table-wrap"><table><thead><tr><th>Incluir</th><th>Municipio y fuente</th><th>Predictores</th><th>Consultas</th></tr></thead><tbody>{records.map(r=>{const complete=features.length===27&&features.every(f=>r.data[f]!=null)&&r.data.consultas!=null;const choice=choices[r.id];return <tr key={r.id}><td><input type="checkbox" aria-label={`Incluir ${r.data.nom_mpio} ${r.year}`} checked={!!choice} disabled={!complete} onChange={e=>{setChoices(current=>{const next={...current};if(e.target.checked)next[r.id]={label:"",label_source:""};else delete next[r.id];return next})}}/></td><td><strong>{r.data.nom_mpio}</strong><small>{r.code} · {r.year} · {r.source}</small></td><td>{features.filter(f=>r.data[f]!=null).length} / 27</td><td>{r.data.consultas??"Pendiente"}</td></tr>})}</tbody></table></div>:<p className="empty">No hay registros operativos para seleccionar.</p>}
    </section>
    <div className="lab-heading"><h2>Experimentos</h2><p>El conjunto de prueba se evalúa después de seleccionar el candidato en validación.</p></div>
    {!experiments.length&&<div className="panel"><p className="subtle">Crea una versión del dataset para comenzar tu primer experimento.</p></div>}
    {experiments.map(exp=><section className="panel experiment" key={exp.id}>
      <div className="experiment-head"><div><div className="overline"><span/> DATASET #{exp.dataset_id}</div><h2>Experimento #{exp.id}</h2><p className="subtle">{new Date(exp.created).toLocaleString("es-CO")} · {exp.info.selected??"Entrenamiento"}</p></div><span className="table-tag">{exp.status}{active===exp.id?" · PUBLICADO":""}</span></div>
      {exp.info.error&&<div className="alert">{exp.info.error}</div>}
      {exp.info.split&&<div className="split-row">{Object.entries(exp.info.split).map(([name,part])=><div key={name}><strong>{name==="train"?"Entrenamiento":name==="val"?"Validación":"Prueba"}</strong><span>{part.municipalities} municipios · {part.records} registros</span></div>)}</div>}
      {exp.info.validation&&Object.entries(exp.info.validation).map(([name,score])=><Metrics key={name} name={`Validación · ${name}${exp.info.selected===name?" · seleccionado":""}`} score={score}/>)}
      {exp.info.test&&<Metrics name="Prueba · candidato seleccionado" score={exp.info.test}/>}
      {exp.status==="completado"&&<div className="lab-buttons"><button className="secondary" disabled={busy||!!exp.info.test} onClick={()=>act(()=>request(`/experiments/${exp.id}/test`,{method:"POST"}),"Evaluación de prueba calculada.")}>{exp.info.test?"Prueba evaluada":"Evaluar en prueba"}</button><button className="primary" disabled={busy||!exp.info.test||active===exp.id} onClick={()=>act(async()=>{await request(`/experiments/${exp.id}/publish`,{method:"POST"});onPublished()},"Modelo publicado. Las nuevas consultas usarán esta versión.")}>{active===exp.id?"Modelo publicado":"Publicar modelo"}</button></div>}
    </section>)}
  </>
}
