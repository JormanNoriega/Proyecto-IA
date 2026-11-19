import {useEffect, useState} from "react";

type Row = {fila:number; cod_mpio:string; municipio:string; a_o:number|null; errores:string[]; advertencias:string[]; elegibilidad:string};
type Preview = {token:string; rows:Row[]};
type Field = {campo:string; descripcion:string; unidad:string; origen_historico:string; estado:string};
type Schema = {columns:string[]; features:string[]; instructions:string; dictionary:Field[]};
type RecordItem = {id:number; code:string; year:number; source:string; reference_date:string; created:string; created_by:string; data:Record<string, string|number|null>};
type Revision = {data:Record<string,string|number|null>; changed_at:string; changed_by:string; action:string};
type Exploratory = {id:number; created:string; created_by:string; model:string; model_sha256:string; probability:number; warning:string; data:Record<string,string|number|null>};
type Props = {request:(path:string, options?:RequestInit)=>Promise<any>; json:(body:unknown)=>RequestInit};

export default function DataManagement({request,json}:Props) {
  const [schema,setSchema]=useState<Schema|null>(null);
  const [records,setRecords]=useState<RecordItem[]>([]);
  const [file,setFile]=useState<File|null>(null);
  const [form,setForm]=useState<Record<string,string>>({cod_mpio:"",a_o:"2026",fuente:"",fecha_referencia:""});
  const [preview,setPreview]=useState<Preview|null>(null);
  const [editing,setEditing]=useState<number|null>(null);
  const [previewCorrection,setPreviewCorrection]=useState(false);
  const [history,setHistory]=useState<{title:string; items:Revision[]}|null>(null);
  const [predictions,setPredictions]=useState<{title:string; items:Exploratory[]}|null>(null);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [busy,setBusy]=useState(false);
  async function loadRecords(){setRecords(await request("/data/records"))}
  useEffect(()=>{request("/data/schema").then(setSchema).catch((e:Error)=>setError(e.message));loadRecords().catch((e:Error)=>setError(e.message))},[]);
  async function validateFile(){
    if(!file)return;
    setBusy(true);setError("");setNotice("");setPreview(null);
    try {const data=new FormData();data.append("file",file);setPreviewCorrection(false);setPreview(await request("/data/preview",{method:"POST",body:data}))}
    catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  async function validateForm(e:React.FormEvent){
    e.preventDefault();setBusy(true);setError("");setNotice("");setPreview(null);
    try{setPreviewCorrection(editing!==null);setPreview(await request(editing===null?"/data/preview-record":`/data/records/${editing}/preview`,json(form)))}
    catch(err){setError((err as Error).message)}finally{setBusy(false)}
  }
  async function confirm(){
    if(!preview)return;
    setBusy(true);setError("");
    try{const path=previewCorrection?`/data/corrections/${encodeURIComponent(preview.token)}/confirm`:`/data/confirm/${encodeURIComponent(preview.token)}`;const result=await request(path,{method:"POST"});setNotice(previewCorrection?"Corrección guardada con historial. No se entrenó ni publicó un modelo.":`${result.guardados} registros guardados; ${result.rechazados} rechazados. No se entrenó ni publicó un modelo.`);setPreview(null);if(previewCorrection){setEditing(null);setForm({cod_mpio:"",a_o:"2026",fuente:"",fecha_referencia:""});setHistory(null)}await loadRecords()}
    catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  function editRecord(record:RecordItem){
    const next:Record<string,string>={};
    for(const field of schema?.columns??[])next[field]=String(record.data[field]??"");
    setForm(next);setEditing(record.id);setPreview(null);setNotice("");setError("");
    document.getElementById("registro-individual")?.scrollIntoView({behavior:"smooth",block:"start"});
  }
  async function showHistory(record:RecordItem){
    try{setError("");setHistory({title:`${record.data.nom_mpio} · ${record.year}`,items:await request(`/data/records/${record.id}/history`)})}
    catch(e){setError((e as Error).message)}
  }
  async function showPredictions(record:RecordItem){
    try{setError("");setPredictions({title:`${record.data.nom_mpio} · ${record.year}`,items:await request(`/data/records/${record.id}/exploratory-predictions`)})}
    catch(e){setError((e as Error).message)}
  }
  async function explore(record:RecordItem){
    setBusy(true);setError("");setNotice("");
    try{await request(`/data/records/${record.id}/exploratory-prediction`,{method:"POST"});await showPredictions(record);setNotice("Prueba exploratoria guardada. No es una predicción validada ni se incorpora a las jornadas.")}
    catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  const valid=preview?.rows.filter(r=>!r.errores.length).length??0;
  return <>
    <div className="heading-row"><div><div className="overline"><span/> GESTIÓN DE DATOS</div><h1>Datos municipales.</h1><p>Registra información por municipio y año, revisa su procedencia y confirma antes de guardar.</p></div></div>
    <div className="info-box"><p>Los registros operativos se almacenan por separado. Los completos pueden consultarse en Vista territorial y seleccionarse para jornadas; también pueden incorporarse al entrenamiento con una etiqueta en Laboratorio IA. Las estimaciones requieren revisión humana.</p></div>
    {error&&<div className="alert" role="alert">{error}</div>}{notice&&<div className="success" role="status">{notice}</div>}
    <div className="two-cols">
      <section className="panel"><div className="panel-title"><div><h2>Importación masiva</h2><p>Descarga la plantilla, complétala y revisa el resultado antes de confirmar.</p></div></div>
        <div className="data-actions"><a href="/api/v1/data/template/xlsx">Descargar Excel</a><a href="/api/v1/data/template/csv">Descargar CSV</a><a href="/api/v1/data/template/diccionario.csv">Diccionario CSV</a></div>
        <p className="footnote">{schema?.instructions}</p>
        <label className="file-picker"><input type="file" accept=".csv,.xlsx" onChange={e=>{setFile(e.target.files?.[0]??null);setPreview(null)}}/><strong>{file?.name??"Seleccionar archivo"}</strong><small>CSV UTF-8 o Excel · máximo 2 MB y 2.000 filas</small></label>
        <button type="button" className="primary full" disabled={!file||busy} onClick={validateFile}>{busy?"Validando…":"Validar y previsualizar"}</button>
      </section>
      <section className="panel" id="registro-individual"><div className="panel-title"><div><h2>{editing===null?"Registro individual":"Corregir registro"}</h2><p>{editing===null?"El código municipal debe incluir los cinco dígitos DIVIPOLA.":"El municipio y el año no se pueden cambiar; la corrección quedará en el historial."}</p></div></div>
        <form onSubmit={validateForm}><div className="form-grid">
          <label>Código municipal<input required readOnly={editing!==null} inputMode="numeric" maxLength={5} value={form.cod_mpio} onChange={e=>setForm({...form,cod_mpio:e.target.value})} placeholder="Ej. 20001"/></label>
          <label>Año<input required readOnly={editing!==null} type="number" min="1900" max="2100" value={form.a_o} onChange={e=>setForm({...form,a_o:e.target.value})}/></label>
          <label>Fuente<input required maxLength={500} value={form.fuente} onChange={e=>setForm({...form,fuente:e.target.value})} placeholder="Entidad y conjunto de datos"/></label>
          <label>Fecha de referencia<input required type="date" value={form.fecha_referencia} onChange={e=>setForm({...form,fecha_referencia:e.target.value})}/></label>
          <label>Consultas del año<input type="number" min="0" step="1" value={form.consultas??""} onChange={e=>setForm({...form,consultas:e.target.value})}/><small>Opcional para guardar; necesario para calcular la prioridad.</small></label>
        </div><div className="data-fields"><h3>Indicadores opcionales ({schema?.features.length??27})</h3><p className="footnote">La plantilla incluye identificación, consultas y 27 indicadores. Puedes guardar campos vacíos. No inventes valores; verifica la equivalencia para años nuevos.</p>{!schema&&<p role="status">Cargando indicadores…</p>}<div className="form-grid">{schema?.dictionary.filter(f=>schema.features.includes(f.campo)).map(f=><label key={f.campo}>{f.descripcion} ({f.unidad})<input aria-label={`${f.descripcion}, ${f.campo}`} type="number" step="any" value={form[f.campo]??""} onChange={e=>setForm({...form,[f.campo]:e.target.value})}/><small>{f.campo} · {f.origen_historico}</small></label>)}</div></div>
        <button className="primary full" disabled={busy}>{busy?"Validando…":editing===null?"Revisar registro":"Revisar corrección"}</button>{editing!==null&&<button type="button" onClick={()=>{setEditing(null);setForm({cod_mpio:"",a_o:"2026",fuente:"",fecha_referencia:""});setPreview(null)}}>Cancelar corrección</button>}</form>
      </section>
    </div>
    {preview&&<section className="panel data-preview"><h2>{previewCorrection?"Vista previa de corrección":"Vista previa"}</h2><p>{valid} filas válidas · {preview.rows.length-valid} con errores. Solo se guardarán las válidas al confirmar.</p><div className="table-wrap"><table><thead><tr><th>Fila</th><th>Municipio · año</th><th>Estado y observaciones</th></tr></thead><tbody>{preview.rows.map(r=><tr key={r.fila}><td>{r.fila}</td><td><strong>{r.municipio||r.cod_mpio||"Sin municipio"}</strong><small>{r.cod_mpio} · {r.a_o??"sin año"}</small></td><td><strong>{r.errores.length?"Con errores":r.elegibilidad==="incompleto"?"Incompleto":"Requiere revisión de IA"}</strong>{[...r.errores,...r.advertencias].map((s,i)=><small key={i}>{s}</small>)}</td></tr>)}</tbody></table></div><div className="data-actions"><button type="button" className="primary" disabled={!valid||busy} onClick={confirm}>{previewCorrection?"Confirmar corrección":`Confirmar ${valid} registros válidos`}</button><button type="button" onClick={()=>setPreview(null)}>Cancelar</button></div></section>}
    <section className="panel data-preview"><h2>Registros operativos guardados</h2><p>Últimos 500 registros. El histórico y los registros de la importación anterior no se modifican.</p>{records.length?<div className="table-wrap"><table><thead><tr><th>Municipio · año</th><th>Fuente y referencia</th><th>Creado por</th><th>Predictores</th><th>Acciones</th></tr></thead><tbody>{records.map(r=><tr key={`${r.code}-${r.year}`}><td><strong>{r.data.nom_mpio}</strong><small>{r.code} · {r.year}</small></td><td>{r.source}<small>{r.reference_date}</small></td><td>{r.created_by}<small>{r.created.slice(0,10)}</small></td><td>{schema?.features.filter(f=>r.data[f]!=null).length??0} / {schema?.features.length??27}</td><td><div className="record-actions">
      <button className="primary" type="button" onClick={()=>editRecord(r)}>Corregir</button>
      <button className="primary" type="button" onClick={()=>showHistory(r)}>Historial</button>
      <button className="primary" type="button" disabled={busy||!schema||schema.features.some(f=>r.data[f]==null)} onClick={()=>explore(r)}>Probar IA</button>
      <button className="primary" type="button" onClick={()=>showPredictions(r)}>Ver pruebas</button>
    </div></td></tr>)}</tbody></table></div>:<p className="empty">Aún no hay registros operativos en este módulo.</p>}</section>
    {history&&<section className="panel data-preview"><h2>Historial: {history.title}</h2><p>Versiones completas en orden de registro.</p>{history.items.map((item,index)=><details key={index}><summary>{item.action} · {item.changed_by} · {item.changed_at}</summary><dl>{Object.entries(item.data).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value===null?"—":String(value)}</dd></div>)}</dl></details>)}<button type="button" onClick={()=>setHistory(null)}>Cerrar historial</button></section>}
    {predictions&&<section className="panel data-preview"><h2>Pruebas exploratorias: {predictions.title}</h2><p>Son pruebas históricas del modelo sobre los valores capturados; no son pronósticos ni resultados validados para decisiones.</p>{predictions.items.length?predictions.items.map(p=><details key={p.id}><summary>#{p.id} · {(p.probability*100).toFixed(1)}% · {p.created.slice(0,10)} · {p.model}</summary><p className="footnote">{p.warning}</p><p className="footnote">Modelo SHA-256: {p.model_sha256} · Usuario: {p.created_by}</p><dl>{Object.entries(p.data).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value===null?"—":String(value)}</dd></div>)}</dl></details>):<p>No hay pruebas para este registro.</p>}<button type="button" onClick={()=>setPredictions(null)}>Cerrar pruebas</button></section>}
  </>;
}
