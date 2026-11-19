import { useState } from "react";
import { Activity, ArrowRight, MapPinned } from "lucide-react";

type Item = {cod_mpio:string; nom_mpio:string};
type Props = {items:Item[]; year:number; request:(path:string,options?:RequestInit)=>Promise<any>; json:(body:unknown)=>RequestInit};
const labels:Record<string,string> = {
  latitud:"Latitud", longitud:"Longitud", poblacion:"Población", pct_rural_disperso:"Rural disperso (%)", banda_pob:"Banda poblacional",
  nbi_total:"NBI total (%)", nbi_miseria:"NBI miseria (%)", nbi_vivienda:"NBI vivienda (%)", nbi_servicios:"NBI servicios (%)", nbi_hacinamiento:"NBI hacinamiento (%)", nbi_inasistencia:"NBI inasistencia (%)", nbi_dependencia:"NBI dependencia (%)",
  nbi_rural:"NBI rural (%)", nbi_rural_miseria:"NBI rural miseria (%)", nbi_rural_servicios:"NBI rural servicios (%)", nbi_rural_hacinamiento:"NBI rural hacinamiento (%)",
  n_sedes:"Sedes de salud", n_sedes_ese:"Sedes ESE", sedes_10k_hab:"Sedes por 10.000 habitantes", n_resguardos:"Resguardos", pob_resguardos:"Población en resguardos", n_comunidades:"Comunidades",
  pct_cap_O:"Capítulo O (%)", pct_cap_A:"Capítulo A (%)", pct_cap_J:"Capítulo J (%)", pct_cap_K:"Capítulo K (%)", pct_cap_Z:"Capítulo Z (%)"
};

export default function Prediction({items,year,request,json}:Props) {
  const [code,setCode]=useState(items[0]?.cod_mpio??"");
  const [features,setFeatures]=useState<Record<string,string>>({});
  const [name,setName]=useState("");
  const [result,setResult]=useState<any>(null);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const selected=items.some(item=>item.cod_mpio===code)?code:items[0]?.cod_mpio??"";
  async function load(){
    setBusy(true);setError("");setResult(null);
    try {const d=await request(`/predictions/template?code=${encodeURIComponent(selected)}&year=${year}`);setName(d.name);setFeatures(Object.fromEntries(Object.entries(d.features).map(([k,v])=>[k,v==null?"":String(v)])))}catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  async function predict(){
    setBusy(true);setError("");
    try {setResult(await request("/predictions",json(features)))}catch(e){setError((e as Error).message);setResult(null)}finally{setBusy(false)}
  }
  return <>
    <div className="heading-row"><div><div className="overline"><span/> CONSULTA DE PREDICCIÓN</div><h1>Explora una posibilidad.</h1><p>Carga los datos de un municipio y modifica sus variables antes de consultar el modelo.</p></div></div>
    {error&&<div className="alert" role="alert">{error}</div>}
    <div className="two-cols"><section className="panel"><div className="panel-title"><MapPinned/><div><h2>Datos de referencia</h2><p>Usa un municipio del filtro territorial actual como punto de partida.</p></div></div><label className="lab-label">Municipio · año {year}<select value={selected} onChange={e=>setCode(e.target.value)}>{items.map(x=><option key={x.cod_mpio} value={x.cod_mpio}>{x.nom_mpio} · {x.cod_mpio}</option>)}</select></label><button className="secondary full" disabled={!selected||busy} onClick={load}>Cargar variables</button>{name&&<p className="footnote">Editando una copia de {name}, {year}. Los cambios no se agregan al dataset.</p>}</section>
    <section className="panel side-explainer"><span className="panel-icon"><Activity/></span><h2>{result?"Resultado estimado":"Predicción responsable"}</h2>{result?<><div className="prediction-score">{(result.probability*100).toFixed(1)}%</div><strong>{result.priority_high?"Prioridad alta estimada":"Prioridad regular estimada"}</strong><p>{result.model} · Umbral {(result.threshold*100).toFixed(0)}%</p><p>{result.warning}</p></>:<><p>El resultado responde a las variables introducidas; no es un diagnóstico ni reemplaza la evaluación del territorio.</p><p>Necesitas al menos 20 variables y una población válida.</p></>}</section></div>
    {name&&<section className="panel prediction-form"><h2>Variables para la consulta</h2><p className="subtle">Valores faltantes se tratan con el preprocesamiento del modelo activo. Revisa unidades y fuente.</p><div className="feature-grid">{Object.entries(labels).map(([key,label])=><label key={key}>{label}<input type="number" step="any" value={features[key]??""} onChange={e=>setFeatures({...features,[key]:e.target.value})}/></label>)}</div><button className="primary" disabled={busy} onClick={predict}>{busy?"Calculando…":"Consultar modelo"} <ArrowRight size={16}/></button></section>}
  </>
}
