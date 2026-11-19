/* THESIS: un puesto de observación territorial donde el mapa y la tabla comparten protagonismo.
   OWN-WORLD: verde profundo, superficies blancas y acentos lima; lenguaje de cartografía sanitaria.
   STORY: explorar, comprender y planear con evidencia histórica y límites explícitos.
   FIRST VIEWPORT: navegación lateral, indicadores compactos y mapa operativo con ficha de selección. */
import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import * as maplibregl from "maplibre-gl";
import mapWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";
import { Activity, ArrowDownToLine, ArrowRight, Check, ChevronRight, CircleHelp, Database, FileUp, LayoutDashboard, LogOut, MapPinned, Menu, Plus, ShieldCheck, SlidersHorizontal, Users, X } from "lucide-react";
import Laboratory from "./Laboratory";
import DataManagement from "./DataManagement";
import Prediction from "./Prediction";
import Bases from "./Bases";
import Journeys from "./Journeys";
import {useDepartmentOutline} from "./useDepartmentOutline";
import {useMunicipalityOutline} from "./useMunicipalityOutline";
import {useMunicipalityAreas} from "./useMunicipalityAreas";
import "./styles.css";

// MapLibre 6 requires an explicit worker URL when bundled with Vite.
maplibregl.setWorkerUrl(mapWorkerUrl);

type User = {username:string; role:string};
type Municipality = {cod_mpio:string; nom_mpio:string; cod_dpto:string; a_o:number; latitud:number|null; longitud:number|null; poblacion:number|null; pct_rural_disperso:number|null; nbi_rural:number|null; n_resguardos:number|null; es_hub:number|null; probability:number; fuente?:string; fecha_referencia?:string};
type MapBase = {id:number;name:string;municipality:string;department:string;latitude:number;longitude:number;geo_status:string;geo_review?:{message:string}};
type Plan = {id:number; selected:(Municipality & {distance_km:number})[]; distance_provider:string};
type OperationalRecord = {id:number; code:string; year:number; source:string; reference_date:string; created_by:string; data:Record<string,string|number|null>};
const API = "/api/v1";
async function request(path:string, options:RequestInit = {}) {
  const response = await fetch(API + path, {...options, credentials:"include"});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? "Ocurrió un error"));
  return data;
}
const json = (body:unknown):RequestInit => ({method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
const num = (n:number|null|undefined) => n == null ? "—" : new Intl.NumberFormat("es-CO", {maximumFractionDigits:1}).format(n);
const pct = (n:number|null|undefined) => n == null ? "—" : `${(n*100).toFixed(1)}%`;
const departmentNames:Record<string,string> = {
  "05":"Antioquia", "08":"Atlántico", "11":"Bogotá D. C.", "13":"Bolívar", "15":"Boyacá",
  "17":"Caldas", "18":"Caquetá", "19":"Cauca", "20":"Cesar", "23":"Córdoba",
  "25":"Cundinamarca", "27":"Chocó", "41":"Huila", "44":"La Guajira", "47":"Magdalena",
  "50":"Meta", "52":"Nariño", "54":"Norte de Santander", "63":"Quindío", "66":"Risaralda",
  "68":"Santander", "70":"Sucre", "73":"Tolima", "76":"Valle del Cauca", "81":"Arauca",
  "85":"Casanare", "86":"Putumayo", "88":"San Andrés y Providencia", "91":"Amazonas",
  "94":"Guainía", "95":"Guaviare", "97":"Vaupés", "99":"Vichada",
};
const departmentName = (code:string) => departmentNames[code] ?? `Código ${code}`;

function MapView({items, allItems, selected, onSelect, plan, department, bases, showPoints}: {items:Municipality[];allItems:Municipality[];selected:Municipality|null;onSelect:(m:Municipality)=>void;plan:Plan|null;department:string;bases:MapBase[];showPoints:boolean}) {
  const container = useRef<HTMLDivElement>(null); const map = useRef<maplibregl.Map|null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const [mapStatus,setMapStatus] = useState<"loading"|"ready"|"unavailable">("loading");
  useEffect(() => {
    if (!container.current) return;
    let failures = 0;
    const m = new maplibregl.Map({container:container.current, style:"https://tiles.openfreemap.org/styles/positron", center:[-73.5,9.7], zoom:6.4});
    m.on("idle", () => { if (failures === 0) setMapStatus("ready"); });
    m.on("error", (event) => {
      console.warn("Mapa base:", event.error);
      failures += 1;
      if (failures >= 3) setMapStatus("unavailable");
    });
    m.addControl(new maplibregl.NavigationControl({showCompass:false}), "bottom-right");
    map.current=m;
    return () => {
      m.remove(); map.current=null;
    };
  }, []);
  const outlineError=useDepartmentOutline(map,department,request,!selected);
  const municipalityOutlineError=useMunicipalityOutline(map,selected?.cod_mpio?.startsWith(department)?selected.cod_mpio:"",request);
  const [areaNotice,setAreaNotice]=useState("");
  const areaError=useMunicipalityAreas(map,department,selected?.cod_mpio??"",code=>{
    const item=allItems.find(m=>m.cod_mpio===code);
    if(item){setAreaNotice("");onSelect(item)}
    else setAreaNotice(`El municipio ${code} no tiene predicción disponible para el año seleccionado.`);
  });
  useEffect(()=>setAreaNotice(""),[department,allItems]);
  useEffect(()=>{
    const m=map.current;
    if(!m)return;
    const baseMarkers=bases.filter(b=>Number.isFinite(b.latitude)&&Number.isFinite(b.longitude)&&Math.abs(b.latitude)<=90&&Math.abs(b.longitude)<=180).map(b=>{
      const el=document.createElement("button");
      el.type="button";el.className="territory-base-marker";
      el.setAttribute("aria-label",`Base ${b.name}, ${b.municipality}, ${b.department}. ${b.geo_status==="VALIDADA"?"Ubicación validada":"Ubicación pendiente de revisión"}`);
      const popup=new maplibregl.Popup({offset:18}).setText(`Base: ${b.name} · ${b.municipality}, ${b.department} · ${b.geo_status==="VALIDADA"?"Ubicación validada":"Ubicación pendiente de revisión"}`);
      return new maplibregl.Marker({element:el}).setLngLat([b.longitude,b.latitude]).setPopup(popup).addTo(m);
    });
    return ()=>baseMarkers.forEach(marker=>marker.remove());
  },[bases]);
  useEffect(() => {
    if (!map.current) return;
    markers.current.forEach(m => m.remove()); markers.current=[];
    const valid=showPoints?items.filter(m=>m.latitud != null && m.longitud != null):[];
    valid.forEach(item => {
      const el=document.createElement("button");
      el.className=`map-marker ${selected?.cod_mpio===item.cod_mpio?"is-selected":""} ${plan?.selected.some(x=>x.cod_mpio===item.cod_mpio)?"is-planned":""}`;
      el.style.setProperty("--strength", String(Math.max(.3,item.probability)));
      el.setAttribute("aria-label",`${item.nom_mpio}: ${pct(item.probability)}`);
      el.onclick=()=>onSelect(item);
      markers.current.push(new maplibregl.Marker({element:el}).setLngLat([item.longitud!,item.latitud!]).addTo(map.current!));
    });
    return () => {markers.current.forEach(m=>m.remove());markers.current=[]};
  }, [items, selected, plan, showPoints]);
  return <><div className="map" ref={container} aria-label="Mapa de municipios. La tabla presenta los mismos resultados." />
    {outlineError&&<div className="map-notice map-notice-error" role="status">{outlineError}</div>}
    {municipalityOutlineError&&<div className="map-notice map-notice-error" role="status">{municipalityOutlineError}</div>}
    {(areaError||areaNotice)&&<div className="map-notice map-notice-error" role="status">{areaError||areaNotice}</div>}
    {mapStatus==="unavailable"&&<div className="map-notice map-notice-error" role="status">Algunos recursos del mapa no cargaron. Comprueba tu conexión; la tabla sigue disponible. <button onClick={()=>window.location.reload()}>Reintentar</button></div>}
  </>;
}

function TerritorialRecords({department}:{department:string}) {
  const [year,setYear]=useState(new Date().getFullYear());
  const [records,setRecords]=useState<OperationalRecord[]>([]);
  const [status,setStatus]=useState("");
  useEffect(()=>{
    let active=true;
    setRecords([]);
    if(!Number.isInteger(year)||year<1900||year>2100){setStatus("Indica un año entre 1900 y 2100.");return}
    setStatus("Cargando registros operativos…");
    request(`/data/territorial-records?department=${encodeURIComponent(department)}&year=${year}`)
      .then(data=>{if(active){setRecords(data);setStatus("")}})
      .catch((e:Error)=>{if(active)setStatus(e.message)});
    return ()=>{active=false};
  },[department,year]);
  return <section className="panel data-preview">
    <h2>Registros operativos declarados</h2>
    <p>Consulta separada para {departmentName(department)}. No son predicciones ni candidatos para jornadas; la fuente y fecha corresponden al registro completo, no a cada indicador.</p>
    <label>Año de consulta operativa <input type="number" min="1900" max="2100" value={Number.isNaN(year)?"":year} onChange={e=>setYear(e.target.value?Number(e.target.value):NaN)}/></label>
    {status?<p role="status">{status}</p>:records.length?<div className="table-wrap"><table><thead><tr><th>Municipio · año</th><th>Fuente declarada</th><th>Datos registrados</th></tr></thead><tbody>{records.map(r=><tr key={r.id}><td><strong>{r.data.nom_mpio}</strong><small>{r.code} · {r.year}</small></td><td>{r.source}<small>Referencia: {r.reference_date} · Creado por {r.created_by}</small></td><td><details><summary>Consultar indicadores</summary><dl>{Object.entries(r.data).filter(([key])=>!["cod_mpio","cod_dpto","nom_mpio","a_o","fuente","fecha_referencia"].includes(key)).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value==null?"Sin dato":String(value)}</dd></div>)}</dl></details></td></tr>)}</tbody></table></div>:<p className="empty">No hay registros operativos para este departamento y año.</p>}
  </section>;
}

function App(){
  const [user,setUser]=useState<User|null>(null); const [checking,setChecking]=useState(true);
  const [page,setPage]=useState("mapa"); const [menu,setMenu]=useState(false);
  const [items,setItems]=useState<Municipality[]>([]); const [selected,setSelected]=useState<Municipality|null>(null);
  const [search,setSearch]=useState(""); const [priorityFilter,setPriorityFilter]=useState("all"); const [hubFilter,setHubFilter]=useState("all"); const [showPoints,setShowPoints]=useState(false);
  const [mapBases,setMapBases]=useState<MapBase[]>([]); const [mapBasesError,setMapBasesError]=useState("");
  const [department,setDepartment]=useState("20"); const [year,setYear]=useState(2021);
  const [catalog,setCatalog]=useState<{departments:string[];years:number[]}>({departments:["20"],years:[2021]});
  const [operationalCatalog,setOperationalCatalog]=useState<{departments:string[];years:number[]}>({departments:[],years:[]});
  const [dataSource,setDataSource]=useState<"historico"|"operativo">("historico");
  const [error,setError]=useState(""); const [loading,setLoading]=useState(false); const [plan,setPlan]=useState<Plan|null>(null);
  const [modelName,setModelName]=useState("Modelo fase 2"); const [revision,setRevision]=useState(0);
  const [brigades,setBrigades]=useState(4); const [distance,setDistance]=useState(350); const [minimum,setMinimum]=useState(0);
  const [newUser,setNewUser]=useState({username:"",password:"",role:"operador"}); const [message,setMessage]=useState("");
  useEffect(()=>{request("/auth/me").then(setUser).catch(()=>{}).finally(()=>setChecking(false))},[]);
  useEffect(()=>{if(user){request("/catalog").then(setCatalog).catch(e=>setError(e.message));request("/operational-catalog").then(setOperationalCatalog).catch(e=>setError(e.message))}},[user,page]);
  useEffect(()=>{
    if(!user||page!=="mapa")return;
    let active=true;
    setMapBasesError("");
    request("/bases").then(data=>{if(active)setMapBases(data)}).catch(()=>{if(active){setMapBases([]);setMapBasesError("No se pudieron cargar las bases registradas.")}});
    return ()=>{active=false};
  },[user,page]);
  useEffect(()=>{
    if(!user)return; setLoading(true);setError("");setPlan(null);
    setSelected(null);
    request(`/${dataSource==="operativo"?"operational-priorities":"priorities"}?department=${encodeURIComponent(department)}&year=${year}`).then(d=>{setItems(d.items);setModelName(d.model??"Sin datos completos")}).catch(e=>{setError(e.message);setItems([])}).finally(()=>setLoading(false));
  },[user,department,year,revision,dataSource]);
  async function runPlan(){setError("");setLoading(true);try{const p=await request("/plans",json({department,year,brigades,max_km:distance,min_resguardos:minimum,lat:10.460472,lon:-73.259398}));setPlan(p);setPage("mapa")}catch(e){setError((e as Error).message)}finally{setLoading(false)}}
  const navigate=(name:string)=>{setPage(name);setMenu(false);setError("");setMessage("")};
  if(checking)return <div className="center-state">Preparando el territorio…</div>;
  if(!user)return <Login onLogin={setUser}/>;
  const average=items.length?items.reduce((s,x)=>s+x.probability,0)/items.length:0;
  const normalize=(value:string)=>value.normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase().trim();
  const filteredItems=items.filter(m=>{
    const matchesSearch=normalize(`${m.nom_mpio} ${m.cod_mpio}`).includes(normalize(search));
    const matchesPriority=priorityFilter==="all"||(priorityFilter==="high"?m.probability>=.5:m.probability<.5);
    const matchesHub=hubFilter==="all"||(hubFilter==="hub"?m.es_hub===1:m.es_hub===0);
    return matchesSearch&&matchesPriority&&matchesHub;
  });
  return <div className="shell">
    <aside className={`sidebar ${menu?"open":""}`}>
      <div className="brand"><div className="brand-symbol"><Activity size={23}/></div><div><strong>territorio<span>salud</span></strong><small>Inteligencia territorial</small></div></div>
      <div className="sidebar-label">ESPACIO DE TRABAJO</div>
      <nav aria-label="Navegación principal">
        <button className={page==="mapa"?"active":""} onClick={()=>navigate("mapa")}><LayoutDashboard size={19}/>Vista territorial <ChevronRight size={15}/></button>
        <button className={page==="prediccion"?"active":""} onClick={()=>navigate("prediccion")}><Activity size={19}/>Consultar modelo</button>
        <button className={page==="jornadas"?"active":""} onClick={()=>navigate("jornadas")}><MapPinned size={19}/>Planificar brigadas</button>
        <button className={page==="bases"?"active":""} onClick={()=>navigate("bases")}><MapPinned size={19}/>Bases operativas</button>
        {user.role==="admin"&&<><div className="sidebar-label inner">ADMINISTRACIÓN</div><button className={page==="datos"?"active":""} onClick={()=>navigate("datos")}><Database size={19}/>Gestión de datos</button><button className={page==="laboratorio"?"active":""} onClick={()=>navigate("laboratorio")}><Activity size={19}/>Laboratorio IA</button><button className={page==="usuarios"?"active":""} onClick={()=>navigate("usuarios")}><Users size={19}/>Usuarios</button></>}
      </nav>
      <div className="sidebar-bottom"><div className="sidebar-note"><ShieldCheck size={19}/><p><strong>Apoyo a decisiones</strong><br/>Los resultados requieren revisión humana.</p></div><button className="profile" onClick={()=>request("/auth/logout",{method:"POST"}).finally(()=>setUser(null))}><span className="avatar">{user.username.slice(0,1).toUpperCase()}</span><span><strong>{user.username}</strong><small>{user.role==="admin"?"Administrador IA":"Usuario operativo"}</small></span><LogOut size={17}/></button></div>
    </aside>
    <main className="main">
      <header className="topbar"><button className="mobile-menu" onClick={()=>setMenu(!menu)} aria-label="Abrir menú"><Menu/></button><div className="breadcrumb">Plataforma <ChevronRight size={14}/> <strong>{page==="mapa"?"Vista territorial":page==="jornadas"||page==="planes"?"Planificar brigadas":page==="bases"?"Bases operativas":page==="prediccion"?"Consultar modelo":page==="datos"?"Gestión de datos":page==="laboratorio"?"Laboratorio IA":"Usuarios"}</strong></div><div className="top-right"><span className="status-dot"/> Sistema local <span className="top-divider"/> <CircleHelp size={18}/></div></header>
      <div className="content">
        {error&&<div className="alert" role="alert">{error}<button onClick={()=>setError("")} aria-label="Cerrar"><X size={16}/></button></div>}
        {message&&<div className="success" role="status"><Check size={16}/>{message}</div>}
        {page==="mapa"&&<>
          <div className="heading-row"><div><div className="overline"><span/> PANORAMA TERRITORIAL</div><h1>Decisiones que llegan más lejos.</h1><p>Explora la prioridad estimada y encuentra dónde orientar tus brigadas.</p></div><button className="primary" onClick={()=>navigate("jornadas")}><Plus size={17}/> Planificar brigadas</button></div>
          <div className="summary-strip">
            <div><span>Municipios analizados</span><strong>{num(items.length)}</strong><small>En el filtro seleccionado</small></div>
            <div><span>Prioridad alta estimada</span><strong>{num(items.filter(x=>x.probability>=.5).length)}</strong><small>Umbral de referencia ≥ 50%</small></div>
            <div><span>Probabilidad promedio</span><strong>{items.length?pct(average):"—"}</strong><small>Salida del modelo activo</small></div>
            <div className="summary-context"><span>FUENTE DE ANÁLISIS</span><strong>{modelName}</strong><small>Datos de referencia · {year}</small></div>
          </div>
          <section className="workspace">
            <div className="section-top"><div><h2>Explorador territorial</h2><p>Pasa el cursor por un municipio para identificarlo y haz clic para fijar su selección. También puedes usar la lista.</p></div><div className="filters"><label><span>Datos</span><select value={dataSource} onChange={e=>{const source=e.target.value as "historico"|"operativo";setDataSource(source);const c=source==="operativo"?operationalCatalog:catalog;if(c.years.length)setYear(c.years[0]);if(c.departments.length&&!c.departments.includes(department))setDepartment(c.departments[0])}}><option value="historico">Históricos del modelo</option><option value="operativo">Operativos declarados</option></select></label><label><span>Departamento</span><select value={department} onChange={e=>setDepartment(e.target.value)}>{(dataSource==="operativo"?operationalCatalog:catalog).departments.map(d=><option key={d} value={d}>{departmentName(d)}</option>)}</select></label><label><span>Año</span><select value={year} onChange={e=>setYear(+e.target.value)}>{(dataSource==="operativo"?operationalCatalog:catalog).years.map(y=><option key={y}>{y}</option>)}</select></label></div></div>
            {dataSource==="operativo"&&<p className="footnote">Datos declarados completos · estimaciones exploratorias no validadas temporalmente. Los registros incompletos no reciben puntuación. No se mezclan con el histórico.</p>}
            <div className="map-options"><label><input type="checkbox" checked={showPoints} onChange={e=>setShowPoints(e.target.checked)}/> Mostrar puntos municipales</label><span>Las bases permanecen visibles en el mapa.</span></div>
            <div className="explorer"><div className="map-wrap"><MapView items={filteredItems} allItems={items} selected={selected} onSelect={setSelected} plan={plan} department={department} bases={mapBases} showPoints={showPoints}/><div className="map-label"><span className="live-dot"/> VISTA GEOGRÁFICA <small>✚ bases{showPoints?" · puntos municipales filtrados":""}</small></div>{showPoints&&<div className="legend"><span>Prioridad estimada</span><i className="dot low"/><small>Menor</small><i className="dot mid"/><i className="dot high"/><small>Mayor</small></div>}</div>
              <div className="detail"><div className="detail-head"><span>DETALLE MUNICIPAL</span><MapPinned size={17}/></div>{selected?<><h3>{selected.nom_mpio}</h3><p className="subtle">Código {selected.cod_mpio} · {selected.a_o}</p><div className="score"><span>Probabilidad estimada de prioridad alta</span><div><strong>{pct(selected.probability)}</strong><span className="tag">{selected.es_hub===1?"HUB":selected.probability>=.5?"ALTA":"REGULAR"}</span></div><div className="bar"><span style={{width:`${selected.probability*100}%`}}/></div><small>Salida del modelo, no diagnóstico clínico.</small></div><dl><div><dt>Población</dt><dd>{num(selected.poblacion)}</dd></div><div><dt>Rural disperso</dt><dd>{selected.pct_rural_disperso==null?"—":`${num(selected.pct_rural_disperso)}%`}</dd></div><div><dt>NBI rural</dt><dd>{selected.nbi_rural==null?"—":`${num(selected.nbi_rural)}%`}</dd></div><div><dt>Resguardos</dt><dd>{num(selected.n_resguardos)}</dd></div></dl>{selected.es_hub===1&&<p className="note">Municipio identificado como hub en los datos históricos; puede participar en la jornada multibase.</p>}</>:<p className="subtle">Selecciona un municipio de la lista para consultar su información.</p>}</div>
            </div>
            {dataSource==="operativo"&&selected&&<p className="footnote">Registro seleccionado: {selected.nom_mpio} · Fuente declarada: {selected.fuente} · Referencia: {selected.fecha_referencia}. La clasificación de hub no se determina con este registro.</p>}
            <details className="territory-bases"><summary>Bases registradas en todos los departamentos ({mapBases.length})</summary><p className="footnote">El mapa se centra en el departamento seleccionado; algunas bases pueden estar fuera del área visible. Una base registrada no confirma disponibilidad de brigadas.</p>{mapBasesError?<p role="status">{mapBasesError}</p>:!mapBases.length?<p className="empty">No hay bases registradas.</p>:<div className="version-list">{mapBases.map(b=><div key={b.id}><span><strong>{b.name}</strong><small>{b.municipality}, {b.department} · {b.latitude}, {b.longitude}<br/>{b.geo_status==="VALIDADA"?"Ubicación validada":"Ubicación pendiente de revisión"}{b.geo_review&&` · ${b.geo_review.message}`}</small></span></div>)}</div>}</details>
            <div className="table-head"><div><h3>Municipios del territorio</h3><p>Selecciona un municipio · ordenados por probabilidad estimada</p></div><span aria-live="polite">{loading?"Cargando…":`${filteredItems.length} de ${items.length} resultados`}</span></div>
            <div className="municipality-filters">
              <label>Buscar municipio o código<input type="search" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Nombre o código DANE"/></label>
              <label>Prioridad estimada<select value={priorityFilter} onChange={e=>setPriorityFilter(e.target.value)}><option value="all">Todas</option><option value="high">Desde 50%</option><option value="lower">Menor de 50%</option></select></label>
              <label>Hub histórico<select value={hubFilter} onChange={e=>setHubFilter(e.target.value)}><option value="all">Todos</option><option value="hub">Identificados como hub</option><option value="nonhub">No identificados como hub</option></select></label>
              <button type="button" onClick={()=>{setSearch("");setPriorityFilter("all");setHubFilter("all")}}>Limpiar filtros</button>
            </div>
            {selected&&!filteredItems.some(m=>m.cod_mpio===selected.cod_mpio)&&<p className="filter-selection-note">La selección actual ({selected.nom_mpio}) está fuera de los filtros de la lista.</p>}
            <div className="table-wrap"><table><thead><tr><th>Municipio</th><th>Población</th><th>Rural disperso</th><th>Probabilidad</th><th>Estado</th></tr></thead><tbody>{filteredItems.map(m=><tr key={m.cod_mpio} tabIndex={0} onClick={()=>setSelected(m)} onKeyDown={e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();setSelected(m)}}} className={selected?.cod_mpio===m.cod_mpio?"selected-row":""}><td><strong>{m.nom_mpio}</strong><small>{m.cod_mpio}</small></td><td>{num(m.poblacion)}</td><td>{m.pct_rural_disperso==null?"—":`${num(m.pct_rural_disperso)}%`}</td><td><strong>{pct(m.probability)}</strong></td><td><span className="table-tag">{m.es_hub===1?"Hub":m.probability>=.5?"Prioridad alta":"Regular"}</span></td></tr>)}</tbody></table>{!loading&&!filteredItems.length&&<p className="empty">{items.length?"Ningún municipio coincide con los filtros. Prueba a modificarlos o limpiarlos.":"No se encontraron datos para este departamento y año."}</p>}</div>
          </section><p className="footnote">Las probabilidades no están calibradas. Los puntos son coordenadas municipales y el contorno es una referencia geoestadística simplificada del DANE.</p>
          {user.role==="admin"&&<TerritorialRecords department={department}/>}
        </>}
        {page==="laboratorio"&&user.role==="admin"&&<Laboratory request={request} json={json} onPublished={()=>setRevision(x=>x+1)}/>}
        {page==="prediccion"&&<Prediction key={`${department}-${year}-${revision}`} items={items} year={year} request={request} json={json}/>}
        {page==="bases"&&<Bases request={request} json={json}/>}
        {page==="jornadas"&&<Journeys request={request} json={json} onBases={()=>navigate("bases")}/>}
        {page==="planes"&&<><div className="heading-row"><div><div className="overline"><span/> PLANIFICACIÓN OPERATIVA</div><h1>Planea con perspectiva.</h1><p>Configura los recursos disponibles para obtener una propuesta de asignación.</p></div></div><div className="two-cols"><section className="panel"><div className="panel-title"><SlidersHorizontal/><div><h2>Configurar escenario</h2><p>La selección considera prioridad, población vulnerable y distancia.</p></div></div><div className="form-grid"><label>Departamento<select value={department} onChange={e=>setDepartment(e.target.value)}>{catalog.departments.map(d=><option key={d} value={d}>{departmentName(d)}</option>)}</select></label><label>Año<select value={year} onChange={e=>setYear(+e.target.value)}>{catalog.years.map(y=><option key={y}>{y}</option>)}</select></label><label>Brigadas disponibles<input type="number" min="1" max="100" value={brigades} onChange={e=>setBrigades(+e.target.value)}/></label><label>Distancia máxima (km)<input type="number" min="1" max="2000" value={distance} onChange={e=>setDistance(+e.target.value)}/></label><label>Destinos mínimos con resguardos<input type="number" min="0" value={minimum} onChange={e=>setMinimum(+e.target.value)}/></label></div><div className="info-box"><MapPinned size={19}/><div><strong>Base: Valledupar</strong><p>10.460472, -73.259398 · La distancia es geográfica de ida (Haversine), no una ruta por carretera.</p></div></div><button className="primary full" disabled={loading} onClick={runPlan}>{loading?"Calculando…":"Generar propuesta"} <ArrowRight size={17}/></button></section><section className="panel side-explainer"><span className="panel-icon"><Activity/></span><h2>Una propuesta, no una orden.</h2><p>El modelo identifica patrones en datos históricos. El optimizador combina esa señal con restricciones para proponer municipios candidatos.</p><ul><li>Los hubs se excluyen de la asignación.</li><li>Las restricciones no se relajan automáticamente.</li><li>La decisión final requiere revisión en territorio.</li></ul></section></div></>}
        {page==="datos"&&user.role==="admin"&&<DataManagement request={request} json={json}/>}
        {page==="usuarios"&&<><div className="heading-row"><div><div className="overline"><span/> CONTROL DE ACCESO</div><h1>Equipo de trabajo.</h1><p>Crea cuentas para quienes necesitan acceder a la plataforma local.</p></div></div><section className="panel narrow"><div className="panel-title"><Users/><div><h2>Crear usuario</h2><p>Las cuentas no tienen registro público.</p></div></div><div className="form-grid"><label>Usuario<input value={newUser.username} onChange={e=>setNewUser({...newUser,username:e.target.value})}/></label><label>Contraseña<input type="password" value={newUser.password} onChange={e=>setNewUser({...newUser,password:e.target.value})}/></label><label>Perfil<select value={newUser.role} onChange={e=>setNewUser({...newUser,role:e.target.value})}><option value="operador">Usuario operativo</option><option value="admin">Administrador IA</option></select></label></div><button className="primary" onClick={async()=>{try{await request("/users",json(newUser));setMessage("Usuario creado correctamente.");setNewUser({username:"",password:"",role:"operador"})}catch(e){setError((e as Error).message)}}}>Crear usuario <ArrowRight size={16}/></button></section></>}
      </div>
    </main>
  </div>
}

function Login({onLogin}:{onLogin:(u:User)=>void}){
  const [username,setUsername]=useState("");const [password,setPassword]=useState("");const [error,setError]=useState("");const [busy,setBusy]=useState(false);
  return <div className="login-page"><div className="login-aside"><div className="brand light"><div className="brand-symbol"><Activity size={23}/></div><div><strong>territorio<span>salud</span></strong><small>Inteligencia territorial</small></div></div><div className="login-copy"><div className="overline"><span/> UNA MEJOR MIRADA AL TERRITORIO</div><h1>Más cerca de donde importa.</h1><p>Datos, inteligencia y planificación para apoyar la llegada de brigadas de salud a los territorios.</p></div><p className="login-caption">UNA HERRAMIENTA DE APOYO A DECISIONES · COLOMBIA</p></div><div className="login-main"><form onSubmit={async e=>{e.preventDefault();setBusy(true);setError("");try{onLogin(await request("/auth/login",json({username,password})))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}><div className="overline dark"><span/> BIENVENIDO</div><h2>Ingresa a tu espacio.</h2><p>Accede con la cuenta asignada por el administrador.</p><label>Usuario<input autoComplete="username" required value={username} onChange={e=>setUsername(e.target.value)} placeholder="Tu nombre de usuario"/></label><label>Contraseña<input type="password" autoComplete="current-password" required value={password} onChange={e=>setPassword(e.target.value)} placeholder="Tu contraseña"/></label>{error&&<div className="alert" role="alert">{error}</div>}<button className="primary full" disabled={busy}>{busy?"Ingresando…":"Ingresar a la plataforma"} <ArrowRight size={17}/></button><small className="login-help">¿Aún no tienes cuenta? Contacta al administrador del sistema.</small></form><div className="login-footer">Territorio Salud <span>·</span> Proyecto de IA</div></div></div>
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App/></React.StrictMode>);
