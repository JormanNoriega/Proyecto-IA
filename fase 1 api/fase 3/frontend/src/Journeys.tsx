import React, {useEffect, useMemo, useRef, useState} from "react";
import * as maplibregl from "maplibre-gl";
import {useDepartmentOutline} from "./useDepartmentOutline";

type Base = {id:number; name:string; municipality:string; department:string; latitude:number; longitude:number; geo_status:string};
type Candidate = {cod_mpio:string; nom_mpio:string; probability:number; latitud:number|null; longitud:number|null; fuente?:string; fecha_referencia?:string};
type Allocation = Candidate & {base_id:number; base_name:string; distance_km:number};
type RoadRoute = {geometry:{type:"LineString"; coordinates:[number,number][]}; distance_km:number; duration_minutes:number};
const allocationKey = (allocation:Allocation) => `${allocation.base_id}:${allocation.cod_mpio}`;
type Journey = {id?:number; draft_token?:string; manually_reviewed?:boolean; parameters:{date:string;department:string;year:number;max_km:number;priority_order?:string[]|null}; selected:Allocation[]; bases:(Base & {brigades:number; unused:number})[]; candidates:Candidate[]; suggested_candidates?:Candidate[]; distance_matrix:{base_id:number;municipality_code:string;distance_km:number|null}[]; model:string; warning:string; objective:string; distance_provider:string; unassigned_municipalities:{code:string; name:string; reason:string}[]; excluded:{code:string; name:string; reason:string}[]};
type Priority = {items:Candidate[]; year:number; model:string; warning:string; notice:string; candidates_hash:string; missing:{code:string;name:string}[]};
type Props = {request:(path:string, options?:RequestInit)=>Promise<any>; json:(body:unknown)=>RequestInit; onBases:()=>void};

function JourneyRanking({title,description,items}:{title:string;description:string;items:Candidate[]}) {
  return <section className="journey-ranking">
    <h4>{title} <span>{items.length}</span></h4>
    <p>{description}</p>
    {items.length?<ol tabIndex={0} aria-label={title}>{items.map((item,index)=><li key={item.cod_mpio}>
      <span className="journey-order-rank" aria-hidden="true">{index+1}</span>
      <span>{item.nom_mpio}</span>
      <span className="journey-ranking-score" aria-label={`Puntaje de IA: ${(item.probability*100).toFixed(1)}%`}>{(item.probability*100).toFixed(1)}%</span>
    </li>)}</ol>:<p>No hay un orden registrado.</p>}
  </section>;
}

function PriorityMap({priority,bases,department,request}:{priority:Priority;bases:Base[];department:string;request:Props["request"]}) {
  const container=useRef<HTMLDivElement>(null);
  const map=useRef<maplibregl.Map|null>(null);
  useEffect(()=>{
    if(!container.current)return;
    const m=new maplibregl.Map({container:container.current,style:"https://tiles.openfreemap.org/styles/positron",center:[-74.3,4.6],zoom:4.4});
    map.current=m;
    m.addControl(new maplibregl.NavigationControl({showCompass:false}),"top-right");
    const markers:maplibregl.Marker[]=[];
    const bounds=new maplibregl.LngLatBounds();
    bases.forEach(b=>{bounds.extend([b.longitude,b.latitude]);markers.push(new maplibregl.Marker({color:"#315e54"}).setLngLat([b.longitude,b.latitude]).setPopup(new maplibregl.Popup().setText(`Base: ${b.name} · ${b.municipality}`)).addTo(m))});
    priority.items.forEach(c=>{if(c.latitud!=null&&c.longitud!=null&&Number.isFinite(c.latitud)&&Number.isFinite(c.longitud)){bounds.extend([c.longitud,c.latitud]);markers.push(new maplibregl.Marker({color:"#b46d2c",scale:.8}).setLngLat([c.longitud,c.latitud]).setPopup(new maplibregl.Popup().setText(`${c.nom_mpio} (${c.cod_mpio}) · Prioridad estimada: ${(c.probability*100).toFixed(1)}%`)).addTo(m))}});
    if(!bounds.isEmpty())m.fitBounds(bounds,{padding:60,maxZoom:9,duration:0});
    return ()=>{markers.forEach(marker=>marker.remove());m.remove();map.current=null};
  },[priority,bases]);
  const error=useDepartmentOutline(map,department,request,false);
  const missing=priority.items.filter(c=>c.latitud==null||c.longitud==null||!Number.isFinite(c.latitud)||!Number.isFinite(c.longitud)).length;
  return <><div className="base-map" ref={container} role="region" aria-label="Mapa de bases seleccionadas y municipios con prioridad estimada; la tabla contiene las prioridades."/>
    <p className="footnote">Verde: base seleccionada. Naranja: municipio con prioridad estimada; pulsa un punto para consultar su porcentaje. Los puntos son referencias, no asignaciones ni rutas.</p>
    {missing>0&&<p className="footnote">{missing} municipios no aparecen en el mapa porque no tienen coordenadas válidas; puedes consultarlos en la tabla.</p>}
    {error&&<p role="status">{error}</p>}</>;
}

function PlanMap({plan,allocation,onSelect,request}:{plan:Journey;allocation:Allocation|undefined;onSelect:(key:string)=>void;request:Props["request"]}) {
  const container=useRef<HTMLDivElement>(null);
  const map=useRef<maplibregl.Map|null>(null);
  const [retry,setRetry]=useState(0);
  const [routeResult,setRouteResult]=useState<{key:string;route?:RoadRoute;error?:string}|null>(null);
  const routeUrl=allocation&&(plan.id||plan.draft_token)?`/journeys/road-route?${new URLSearchParams({
    base_id:String(allocation.base_id),municipality_code:allocation.cod_mpio,
    ...(plan.id?{plan_id:String(plan.id)}:{draft_token:plan.draft_token!}),
  })}`:"";
  const routeState=routeUrl&&routeResult?.key===routeUrl?routeResult:null;
  const route=routeState?.route;
  useEffect(()=>{
    if(!container.current)return;
    const m=new maplibregl.Map({container:container.current,style:"https://tiles.openfreemap.org/styles/positron",center:[-74.3,4.6],zoom:4.4});
    map.current=m;
    m.addControl(new maplibregl.NavigationControl({showCompass:false}),"top-right");
    const markers:maplibregl.Marker[]=[];
    plan.bases.forEach(b=>markers.push(new maplibregl.Marker({color:"#315e54"}).setLngLat([b.longitude,b.latitude]).setPopup(new maplibregl.Popup().setText(`Base: ${b.name}`)).addTo(m)));
    plan.selected.forEach(a=>{
      if(a.latitud==null||a.longitud==null)return;
      const marker=document.createElement("button");
      marker.type="button";
      marker.className="journey-route-marker";
      marker.setAttribute("aria-label",`Mostrar ruta de ${a.base_name} a ${a.nom_mpio}`);
      marker.title=`${a.base_name} → ${a.nom_mpio}`;
      marker.onclick=()=>onSelect(allocationKey(a));
      markers.push(new maplibregl.Marker({element:marker}).setLngLat([a.longitud,a.latitud]).addTo(m));
    });
    const points:[number,number][]=[...plan.bases.map(b=>[b.longitude,b.latitude] as [number,number]),...plan.selected.filter(a=>a.latitud!=null&&a.longitud!=null).map(a=>[a.longitud!,a.latitud!] as [number,number])];
    if(points.length){const bounds=new maplibregl.LngLatBounds();points.forEach(p=>bounds.extend(p));m.fitBounds(bounds,{padding:60,maxZoom:9,duration:0})}
    return ()=>{markers.forEach(marker=>marker.remove());m.remove();map.current=null};
  },[plan,onSelect]);
  useEffect(()=>{
    if(!routeUrl)return;
    const controller=new AbortController();
    // The OSRM table calculation and route lookup share the demo service limit.
    const timer=window.setTimeout(async()=>{
      try {
        const data:RoadRoute=await request(routeUrl,{signal:controller.signal});
        if(!controller.signal.aborted)setRouteResult({key:routeUrl,route:data});
      } catch(error) {
        if(!controller.signal.aborted)setRouteResult({key:routeUrl,error:(error as Error).message});
      }
    },1150);
    return ()=>{window.clearTimeout(timer);controller.abort()};
  },[request,retry,routeUrl]);
  useEffect(()=>{
    const m=map.current;
    if(!route||!m)return;
    const draw=()=>{
      if(m.getSource("journey-road-route"))return;
      m.addSource("journey-road-route",{type:"geojson",data:{type:"Feature",geometry:route.geometry,properties:{}}});
      m.addLayer({id:"journey-road-casing",type:"line",source:"journey-road-route",layout:{"line-join":"round","line-cap":"round"},paint:{"line-color":"#fff","line-width":8}});
      m.addLayer({id:"journey-road-line",type:"line",source:"journey-road-route",layout:{"line-join":"round","line-cap":"round"},paint:{"line-color":"#237653","line-width":5}});
      const bounds=new maplibregl.LngLatBounds();
      route.geometry.coordinates.forEach(point=>bounds.extend(point));
      m.fitBounds(bounds,{padding:50,maxZoom:13,duration:0});
    }
    if(m.isStyleLoaded())draw();
    else {m.once("load",draw);m.once("idle",draw)}
    return ()=>{
      m.off("load",draw);
      m.off("idle",draw);
      if(map.current!==m)return;
      if(m.getLayer("journey-road-line"))m.removeLayer("journey-road-line");
      if(m.getLayer("journey-road-casing"))m.removeLayer("journey-road-casing");
      if(m.getSource("journey-road-route"))m.removeSource("journey-road-route");
    };
  },[plan,route]);
  const error=useDepartmentOutline(map,plan.parameters.department,request,false);
  return <>
    {allocation&&<div className="lab-actions">
      <strong>{allocation.base_name} → {allocation.nom_mpio}</strong>
      {routeUrl&&!routeState&&<p className="footnote" role="status">Consultando ruta vial estimada…</p>}
      {routeState?.error&&<><p className="footnote" role="status">{routeState.error} El mapa conserva los puntos de la asignación.</p><button className="secondary" type="button" onClick={()=>{setRouteResult(null);setRetry(n=>n+1)}}>Reintentar ruta</button></>}
      {route&&<div className="journey-route-summary" role="status">
        <p className="journey-route-summary-title">Ruta vial estimada · Solo ida</p>
        <dl className="journey-route-metrics">
          <div><dt>Distancia por carretera</dt><dd>{route.distance_km.toLocaleString("es-CO",{minimumFractionDigits:1,maximumFractionDigits:1})} <span>km</span></dd></div>
          <div><dt>Tiempo estimado</dt><dd>{Math.round(route.duration_minutes).toLocaleString("es-CO")} <span>min</span></dd></div>
        </dl>
        <p className="footnote">Esta visualización no modifica el plan.</p>
      </div>}
    </div>}
    {!allocation&&plan.selected.length>0&&<p className="footnote">Toca una asignación en la lista o un municipio en el mapa para ver su ruta.</p>}
    <div className="base-map" ref={container} role="region" aria-label="Mapa de bases, municipios asignados y ruta vial cuando está disponible."/>
    <div className="journey-map-legend" aria-label="Referencias del mapa">
      <div className="journey-legend-items">
        <span><i className="journey-legend-dot journey-legend-base" aria-hidden="true"/>Base operativa</span>
        <span><i className="journey-legend-dot journey-legend-destination" aria-hidden="true"/>Municipio asignado</span>
        <span><i className="journey-legend-line" aria-hidden="true"/>Ruta vial estimada</span>
      </div>
      <p>La visualización consulta OSRM con las coordenadas de ambos puntos. No confirma la transitabilidad ni el lugar exacto de atención.</p>
    </div>{error&&<p role="status">{error}</p>}</>;
}

export default function Journeys({request,json,onBases}:Props) {
  const [bases,setBases]=useState<Base[]>([]);
  const [departments,setDepartments]=useState<{code:string;name:string}[]>([]);
  const [department,setDepartment]=useState("20");
  const [date,setDate]=useState("");
  const [dataSource,setDataSource]=useState("historico");
  const [dataYear,setDataYear]=useState(String(new Date().getFullYear()));
  const [maxKm,setMaxKm]=useState("350");
  const [provider,setProvider]=useState("Haversine");
  const [capacity,setCapacity]=useState<Record<number,string>>({});
  const priorityBases=useMemo(()=>bases.filter(b=>capacity[b.id]!==undefined),[bases,capacity]);
  const [priority,setPriority]=useState<Priority|null>(null);
  const [candidateOrder,setCandidateOrder]=useState<string[]>([]);
  const [dragged,setDragged]=useState<string|null>(null);
  const [result,setResult]=useState<Journey|null>(null);
  const [mapAllocation,setMapAllocation]=useState("");
  const [plans,setPlans]=useState<Journey[]>([]);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const [step,setStep]=useState(1);
  const [manualBase,setManualBase]=useState("");
  const [manualMunicipality,setManualMunicipality]=useState("");
  const loadPlans=()=>request("/plans").then((items:Journey[])=>setPlans(items.filter((p:any)=>p.kind==="journey_multibase")));
  useEffect(()=>{Promise.all([request("/bases"),request("/territories"),loadPlans()])
    .then(([b,t])=>{setBases(b);setDepartments(t.departments)}).catch(e=>setError(e.message))},[]);
  async function candidates(e:React.FormEvent) {
    e.preventDefault();setError("");
    const selected=bases.filter(b=>capacity[b.id]!==undefined);
    if(!selected.length){setError("Selecciona al menos una base.");return}
    if(selected.some(b=>!Number.isInteger(Number(capacity[b.id]))||Number(capacity[b.id])<1||Number(capacity[b.id])>100)){setError("Cada base necesita entre 1 y 100 brigadas.");return}
    setBusy(true);
    try{const data:Priority=await request(`/journeys/candidates?department=${department}&data_source=${dataSource}${dataSource==="operativo"?`&year=${encodeURIComponent(dataYear)}`:""}`);setPriority(data);setCandidateOrder(data.items.map(c=>c.cod_mpio));setResult(null);setStep(2)}
    catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  async function preview(){
    const order=candidateOrder;
    if(!priority||!order.length)return;
    setError("");setBusy(true);
    try{
      const selected=bases.filter(b=>capacity[b.id]!==undefined).map(b=>({id:b.id,brigades:Number(capacity[b.id])}));
      const plan:Journey=await request("/journeys/preview",json({date,department,year:priority.year,data_source:dataSource,max_km:Number(maxKm),bases:selected,distance_provider:provider,expected_candidates_hash:priority.candidates_hash,priority_order:order}));
      const confirmed=plan.parameters.priority_order;
      if(!confirmed)throw new Error("El servidor no reconoce el orden de prioridad. Reinicia el backend y vuelve a calcular.");
      const allowed=new Set(order);
      if(confirmed.length!==order.length||confirmed.some((code,index)=>code!==order[index])||plan.selected.some(item=>!allowed.has(item.cod_mpio))){
        throw new Error("La propuesta no respeta el orden de prioridad. No se puede guardar; vuelve a calcular.");
      }
      setResult(plan);setMapAllocation("");setStep(3);
    }catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  async function save(){
    if(!result?.draft_token)return;
    setBusy(true);setError("");
    try{const saved=await request(`/journeys/drafts/${result.draft_token}/save`,json({}));setResult(saved);await loadPlans()}
    catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  async function updateAssignments(assignments:{base_id:number;municipality_code:string}[]){
    if(!result?.draft_token)return;
    setBusy(true);setError("");
    try{const updated=await request(`/journeys/drafts/${result.draft_token}/assignments`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({assignments})});setResult(updated);setManualBase("");setManualMunicipality("")}
    catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  const availableMunicipalities=result&&manualBase?result.candidates.filter(c=>!result.selected.some(a=>a.cod_mpio===c.cod_mpio)&&!result.excluded.some(e=>e.code===c.cod_mpio)&&result.distance_matrix.some(d=>d.base_id===Number(manualBase)&&d.municipality_code===c.cod_mpio&&d.distance_km!==null&&d.distance_km<=result.parameters.max_km)):[];
  function moveCandidate(code:string, target:string) {
    setCandidateOrder(current=>{
      const from=current.indexOf(code), to=current.indexOf(target);
      if(from<0||to<0||from===to)return current;
      const next=[...current];
      next.splice(from,1);
      next.splice(to,0,code);
      return next;
    });
  }
  const candidatesByCode=new Map(priority?.items.map(c=>[c.cod_mpio,c])??[]);
  const previouslyPlanned=new Set(plans.flatMap(plan=>plan.selected.map(item=>item.cod_mpio)));
  const activeAllocation=result?.selected.find(a=>allocationKey(a)===mapAllocation)??(result?.selected.length===1?result.selected[0]:undefined);
  return <>
    <div className="heading-row"><div><div className="overline"><span/> PLANIFICACIÓN OPERATIVA</div><h1>Planificar una jornada</h1><p>Prepara recursos, consulta prioridades y revisa la propuesta antes de guardarla.</p></div></div>
    <div className="journey-steps" aria-label="Progreso de la jornada"><span aria-current={step===1?"step":undefined}>1 · Jornada y recursos</span><span aria-current={step===2?"step":undefined}>2 · Prioridades y distancias</span><span aria-current={step===3?"step":undefined}>3 · Revisar y guardar</span></div>
    {error&&<div className="alert" role="alert">{error}</div>}
    {step===1&&<form className="panel" onSubmit={candidates}>
      <div className="panel-title"><div><h2>Jornada y recursos</h2><p>Elige el departamento de destino, la fecha y una o varias bases.</p></div></div>
      <div className="form-grid"><label>Fecha de la jornada<input type="date" required value={date} onChange={e=>setDate(e.target.value)}/></label>
        <label>Departamento de destino<select value={department} onChange={e=>setDepartment(e.target.value)}>{departments.map(d=><option key={d.code} value={d.code}>{d.name}</option>)}</select></label>
        <label>Datos para prioridades<select value={dataSource} onChange={e=>setDataSource(e.target.value)}><option value="historico">Históricos del modelo</option><option value="operativo">Operativos declarados</option></select></label>
        {dataSource==="operativo"&&<label>Año de datos operativos<input type="number" required min="1900" max="2100" value={dataYear} onChange={e=>setDataYear(e.target.value)}/></label>}</div>
      {dataSource==="operativo"&&<p className="footnote">Solo registros completos. Las estimaciones son exploratorias y no están validadas temporalmente; revisa los datos y la propuesta antes de guardar.</p>}
      <div className="lab-heading"><h2>Bases y brigadas</h2><p>Indica la disponibilidad para esta jornada; registrar una base no implica disponibilidad.</p></div>
      {!bases.length?<div className="info-box"><p>No hay bases registradas. <button type="button" onClick={onBases}>Registrar una base</button></p></div>:
        <div className="journey-bases">{bases.map(b=><div className={`journey-base${capacity[b.id]!==undefined?" is-selected":""}`} key={b.id}>
          <label className="journey-base-choice"><input type="checkbox" checked={capacity[b.id]!==undefined} onChange={e=>setCapacity(old=>{const next={...old};if(e.target.checked)next[b.id]="1";else delete next[b.id];return next})}/><span><strong>{b.name}</strong><small>{b.municipality}, {b.department} · {b.geo_status==="VALIDADA"?"Ubicación validada":"Ubicación pendiente de revisión"}</small></span></label>
          {capacity[b.id]!==undefined&&<label>Brigadas<input aria-label={`Brigadas de ${b.name}`} type="number" required min="1" max="100" step="1" value={capacity[b.id]} onChange={e=>setCapacity({...capacity,[b.id]:e.target.value})}/></label>}
        </div>)}</div>}
      <p className="footnote">Revisa las bases pendientes antes de usarlas; la aplicación no confirma su disponibilidad ni habilitación sanitaria.</p>
      <button className="primary" disabled={busy||!bases.length}>{busy?"Consultando…":"Consultar prioridades"}</button>
    </form>}
    {step===2&&priority&&<><section className="panel"><h2>Mapa de prioridades y bases</h2><p className="subtle">Explora los municipios candidatos y las bases elegidas antes de calcular la propuesta.</p><PriorityMap priority={priority} bases={priorityBases} department={department} request={request}/></section><div className="two-cols">
      <section className="panel"><h2>Municipios candidatos</h2><p className="subtle">Período: <strong>{priority.year}</strong> · Datos {dataSource} · Modelo: {priority.model}</p>
        <p className="footnote">{priority.notice} {priority.warning}</p>
        <p className="footnote">Todos los municipios de la lista se consideran. Arrastra las filas o usa las flechas para indicar a quién se intenta asignar primero. El puntaje de la IA es una referencia, no decide el orden final.</p>
        <div className="table-wrap"><table className="journey-priority-table"><thead><tr><th>Orden</th><th>Municipio</th><th>Puntaje IA</th><th>Ordenar</th></tr></thead><tbody>{candidateOrder.map((code,index)=>{const c=candidatesByCode.get(code);if(!c)return null;return <tr key={code} draggable onDragStart={e=>{setDragged(code);e.dataTransfer.effectAllowed="move";e.dataTransfer.setData("text/plain",code)}} onDragEnd={()=>setDragged(null)} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();moveCandidate(e.dataTransfer.getData("text/plain")||dragged||"",code);setDragged(null)}} className={dragged===code?"journey-dragging":""}>
          <td><span aria-hidden="true" className="journey-drag-handle">⋮⋮</span><span className="journey-order-rank">{index+1}</span></td>
          <td><strong>{c.nom_mpio}</strong><small>{c.cod_mpio}{c.fuente&&` · ${c.fuente} · ${c.fecha_referencia}`}{previouslyPlanned.has(code)&&" · En un plan guardado"}</small></td>
          <td>{(c.probability*100).toFixed(1)}%</td>
          <td><div className="journey-order-buttons"><button type="button" className="secondary" disabled={index===0} aria-label={`Subir ${c.nom_mpio}`} onClick={()=>moveCandidate(code,candidateOrder[index-1])}>↑</button><button type="button" className="secondary" disabled={index===candidateOrder.length-1} aria-label={`Bajar ${c.nom_mpio}`} onClick={()=>moveCandidate(code,candidateOrder[index+1])}>↓</button></div></td>
        </tr>})}</tbody></table></div>
        {!priority.items.length&&<p className="empty">No hay predicciones disponibles para este período.</p>}
        <details><summary>Sin predicción en el catálogo ({priority.missing.length})</summary><p className="footnote">{priority.missing.map(m=>`${m.name} (${m.code})`).join(", ")||"Ninguno."}</p></details>
      </section>
      <section className="panel"><h2>Distancia y propuesta</h2><p className="subtle">Se considera la lista completa en el orden indicado. La distancia se calcula solo de ida.</p>
        <div className="form-grid"><label>Distancia máxima (km)<input type="number" min="0.01" max="2000" step="any" value={maxKm} onChange={e=>setMaxKm(e.target.value)}/></label>
          <label>Proveedor<select value={provider} onChange={e=>setProvider(e.target.value)}><option value="Haversine">Haversine · línea recta</option><option value="OSRM">OSRM · estimación vial</option></select></label></div>
        <p className="footnote">{provider==="Haversine"?"Línea recta: no representa carretera ni acceso.":"Servicio público de demostración para uso razonable no comercial: envía coordenadas al proveedor y puede fallar. Máximo 100 puntos; se excluyen ajustes a más de 1 km de la vía. No garantiza transitabilidad."}</p>
        <p className="footnote">Se respeta la prioridad elegida cuando hay una base con conexión y capacidad. Las asignaciones requieren revisión humana.</p>
        <div className="lab-buttons"><button className="primary" type="button" onClick={()=>setStep(1)}>Volver</button> <button className="primary" type="button" disabled={busy||!candidateOrder.length||!(Number(maxKm)>0&&Number(maxKm)<=2000)} onClick={preview}>{busy?"Calculando…":"Calcular propuesta"}</button></div>
      </section>
    </div></>}
    {step===3&&result&&<div className="two-cols"><section className="panel">
      <h2>{result.id?`Plan guardado #${result.id}`:"Propuesta sin guardar"}</h2><p className="footnote">{result.warning}</p><p className="subtle">Jornada {result.parameters.date} · datos {result.parameters.year} · {result.distance_provider} de ida · modelo {result.model}</p>
      <div className="lab-heading"><h3>Asignaciones</h3></div>
      <p className="footnote">{result.manually_reviewed?"Asignaciones ajustadas por el usuario.":result.parameters.priority_order?"Asignaciones según el orden elegido; revísalas antes de guardar.":"Sugerencia del optimizador; revísala antes de guardar."}</p>
      {result.selected.length?<div className="table-wrap"><table className="journey-allocation-table"><thead><tr><th>Brigada · base → municipio</th><th>Prioridad</th><th>Distancia</th>{!result.id&&<th>Revisión</th>}</tr></thead><tbody>{result.selected.map((a,i)=><tr key={a.cod_mpio} className={a===activeAllocation?"is-route-active":""} onClick={()=>setMapAllocation(allocationKey(a))}>
        <td><button className="journey-allocation-name" type="button" aria-pressed={a===activeAllocation} aria-label={`Brigada ${i+1}: mostrar ruta de ${a.base_name} a ${a.nom_mpio}`}><strong>Brigada {i+1}: {a.base_name} → {a.nom_mpio}</strong><small>{a.cod_mpio}</small></button></td>
        <td>{(a.probability*100).toFixed(1)}%</td><td>{a.distance_km.toFixed(1)} km</td>
        {!result.id&&<td><button className="primary" type="button" disabled={busy} aria-label={`Quitar asignación a ${a.nom_mpio}`} onClick={event=>{event.stopPropagation();updateAssignments(result.selected.filter(s=>s.cod_mpio!==a.cod_mpio).map(s=>({base_id:s.base_id,municipality_code:s.cod_mpio})))}}>Quitar</button></td>}
      </tr>)}</tbody></table></div>:<p>No se asignaron brigadas.</p>}
      {!result.id&&<div className="lab-heading"><h3>Ajustar asignaciones</h3><p className="subtle">Para cambiar una asignación, quítala y elige otra base o municipio. Solo aparecen conexiones válidas dentro del límite.</p><div className="form-grid">
        <label>Base con brigadas disponibles<select value={manualBase} onChange={e=>{setManualBase(e.target.value);setManualMunicipality("")}}><option value="">Selecciona una base</option>{result.bases.filter(b=>b.unused>0).map(b=><option key={b.id} value={b.id}>{b.name} · {b.unused} disponibles</option>)}</select></label>
        <label>Municipio de destino<select value={manualMunicipality} disabled={!manualBase} onChange={e=>setManualMunicipality(e.target.value)}><option value="">Selecciona un municipio</option>{availableMunicipalities.map(c=><option key={c.cod_mpio} value={c.cod_mpio}>{c.nom_mpio} · {(c.probability*100).toFixed(1)}%</option>)}</select></label>
      </div>{manualBase&&!availableMunicipalities.length&&<p className="footnote">No hay municipios disponibles dentro del límite para esta base.</p>}<button className="primary" type="button" disabled={busy||!manualBase||!manualMunicipality||!result.bases.some(b=>b.id===Number(manualBase)&&b.unused>0)} onClick={()=>updateAssignments([...result.selected.map(s=>({base_id:s.base_id,municipality_code:s.cod_mpio})),{base_id:Number(manualBase),municipality_code:manualMunicipality}])}>Añadir asignación</button></div>}
      <div className="lab-heading"><h3>Brigadas sin asignar</h3></div><div className="version-list">{result.bases.map(b=><div key={b.id}><span>{b.name}</span><strong>{b.unused} de {b.brigades}</strong></div>)}</div>
      <div className="journey-explanations">
        <details>
          <summary>Sin asignación en esta jornada ({result.unassigned_municipalities.length+result.excluded.length})</summary>
          <div className="journey-explanation-body">
            <p className="footnote">No recibir una asignación en este plan no impide considerar el municipio en otra jornada.</p>
            {result.unassigned_municipalities.length+result.excluded.length>0?
              <ul className="journey-unassigned-list" tabIndex={0} aria-label="Municipios sin asignación y sus motivos">
                {[...result.unassigned_municipalities,...result.excluded].map(m=><li key={m.code}><strong>{m.name} <span>· {m.code}</span></strong><small>{m.reason}</small></li>)}
              </ul>:<p className="footnote">Todos los municipios considerados tienen una asignación.</p>}
          </div>
        </details>
        <details>
          <summary>Cómo se calculó</summary>
          <div className="journey-explanation-body">
            <dl className="journey-calculation">
              <div><dt>Distancia máxima de ida</dt><dd>{result.parameters.max_km.toLocaleString("es-CO")} km</dd></div>
              <div><dt>Método de distancia</dt><dd>{result.distance_provider==="OSRM"?"OSRM · por carretera":"Haversine · geográfica"}</dd></div>
            </dl>
            <p className="journey-calculation-rule"><strong>Criterio de asignación</strong>{result.objective}</p>
            {result.manually_reviewed&&<p className="footnote">Las asignaciones se ajustaron manualmente después del cálculo inicial.</p>}
          </div>
        </details>
        {result.parameters.priority_order&&<details>
          <summary>Orden elegido y sugerencia inicial</summary>
          <div className="journey-explanation-body journey-rankings">
            <JourneyRanking title="Orden elegido" description="Prioridad definida por ti antes de calcular." items={result.candidates}/>
            <JourneyRanking title="Sugerencia de la IA" description="Orden inicial según el puntaje estimado." items={result.suggested_candidates??[]}/>
          </div>
        </details>}
      </div>
      <div className="lab-buttons"><button className="primary" type="button" onClick={()=>{setStep(1);setResult(null)}}>Nueva jornada</button> {!result.id&&<><button className="primary" type="button" onClick={()=>setStep(2)}>Ajustar</button> <button className="primary" type="button" disabled={busy} onClick={save}>{busy?"Guardando…":"Guardar plan revisado"}</button></>}</div>
    </section><section className="panel"><h2>Mapa de asignaciones</h2><PlanMap key={result.draft_token??result.id} plan={result} allocation={activeAllocation} onSelect={setMapAllocation} request={request}/></section></div>}
    <section className="panel journey-history"><h2>Planes guardados</h2><p className="subtle">Consulta las instantáneas guardadas previamente.</p>{!plans.length?<p className="empty">Aún no hay jornadas guardadas.</p>:<div className="version-list">{plans.map(p=><div key={p.id}><span><strong>Plan #{p.id} · {p.parameters.date}</strong><small>Datos {p.parameters.year} · {p.distance_provider} · {p.selected.length} asignaciones</small></span><button className="primary" type="button" onClick={()=>{setResult(p);setMapAllocation("");setStep(3);setError("")}}>Ver plan</button></div>)}</div>}</section>
  </>;
}
