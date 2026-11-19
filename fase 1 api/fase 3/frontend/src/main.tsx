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
import Prediction from "./Prediction";
import "./styles.css";

// MapLibre 6 requires an explicit worker URL when bundled with Vite.
maplibregl.setWorkerUrl(mapWorkerUrl);

type User = {username:string; role:string};
type Municipality = {cod_mpio:string; nom_mpio:string; cod_dpto:string; a_o:number; latitud:number|null; longitud:number|null; poblacion:number|null; pct_rural_disperso:number|null; nbi_rural:number|null; n_resguardos:number|null; es_hub:number|null; probability:number};
type Plan = {id:number; selected:(Municipality & {distance_km:number})[]; distance_provider:string};
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

function MapView({items, selected, onSelect, plan}: {items:Municipality[];selected:Municipality|null;onSelect:(m:Municipality)=>void;plan:Plan|null}) {
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
  useEffect(() => {
    if (!map.current) return;
    markers.current.forEach(m => m.remove()); markers.current=[];
    const valid=items.filter(m=>m.latitud != null && m.longitud != null);
    valid.forEach(item => {
      const el=document.createElement("button");
      el.className=`map-marker ${selected?.cod_mpio===item.cod_mpio?"is-selected":""} ${plan?.selected.some(x=>x.cod_mpio===item.cod_mpio)?"is-planned":""}`;
      el.style.setProperty("--strength", String(Math.max(.3,item.probability)));
      el.setAttribute("aria-label",`${item.nom_mpio}: ${pct(item.probability)}`);
      el.onclick=()=>onSelect(item);
      markers.current.push(new maplibregl.Marker({element:el}).setLngLat([item.longitud!,item.latitud!]).addTo(map.current!));
    });
    if (valid.length) {
      const bounds = new maplibregl.LngLatBounds();
      valid.forEach(x=>bounds.extend([x.longitud!,x.latitud!]));
      map.current.fitBounds(bounds,{padding:65,maxZoom:8,duration:600});
    }
    return () => {markers.current.forEach(m=>m.remove());markers.current=[]};
  }, [items, selected, plan]);
  return <><div className="map" ref={container} aria-label="Mapa de municipios. La tabla presenta los mismos resultados." />
    {mapStatus==="unavailable"&&<div className="map-notice map-notice-error" role="status">Algunos recursos del mapa no cargaron. Comprueba tu conexión; la tabla y los puntos siguen disponibles. <button onClick={()=>window.location.reload()}>Reintentar</button></div>}
  </>;
}

function App(){
  const [user,setUser]=useState<User|null>(null); const [checking,setChecking]=useState(true);
  const [page,setPage]=useState("mapa"); const [menu,setMenu]=useState(false);
  const [items,setItems]=useState<Municipality[]>([]); const [selected,setSelected]=useState<Municipality|null>(null);
  const [department,setDepartment]=useState("20"); const [year,setYear]=useState(2021);
  const [catalog,setCatalog]=useState<{departments:string[];years:number[]}>({departments:["20"],years:[2021]});
  const [error,setError]=useState(""); const [loading,setLoading]=useState(false); const [plan,setPlan]=useState<Plan|null>(null);
  const [modelName,setModelName]=useState("Modelo fase 2"); const [revision,setRevision]=useState(0);
  const [stats,setStats]=useState<Record<string,number>|null>(null); const [brigades,setBrigades]=useState(4); const [distance,setDistance]=useState(350); const [minimum,setMinimum]=useState(0);
  const [upload,setUpload]=useState<File|null>(null); const [importResult,setImportResult]=useState<any>(null);
  const [record,setRecord]=useState({cod_mpio:"",nom_mpio:"",a_o:"2022",poblacion:""});
  const [newUser,setNewUser]=useState({username:"",password:"",role:"operador"}); const [message,setMessage]=useState("");
  useEffect(()=>{request("/auth/me").then(setUser).catch(()=>{}).finally(()=>setChecking(false))},[]);
  useEffect(()=>{if(user) request("/catalog").then(setCatalog).catch(e=>setError(e.message))},[user]);
  useEffect(()=>{
    if(!user)return; setLoading(true);setError("");setPlan(null);
    request(`/priorities?department=${encodeURIComponent(department)}&year=${year}`).then(d=>{setItems(d.items);setSelected(d.items[0]??null);if(d.model)setModelName(d.model)}).catch(e=>{setError(e.message);setItems([])}).finally(()=>setLoading(false));
  },[user,department,year,revision]);
  useEffect(()=>{if(user?.role==="admin" && page==="datos") request("/statistics").then(setStats).catch(e=>setError(e.message))},[user,page,importResult,message]);
  async function runPlan(){setError("");setLoading(true);try{const p=await request("/plans",json({department,year,brigades,max_km:distance,min_resguardos:minimum,lat:10.460472,lon:-73.259398}));setPlan(p);setPage("mapa")}catch(e){setError((e as Error).message)}finally{setLoading(false)}}
  const navigate=(name:string)=>{setPage(name);setMenu(false);setError("");setMessage("")};
  if(checking)return <div className="center-state">Preparando el territorio…</div>;
  if(!user)return <Login onLogin={setUser}/>;
  const average=items.length?items.reduce((s,x)=>s+x.probability,0)/items.length:0;
  return <div className="shell">
    <aside className={`sidebar ${menu?"open":""}`}>
      <div className="brand"><div className="brand-symbol"><Activity size={23}/></div><div><strong>territorio<span>salud</span></strong><small>Inteligencia territorial</small></div></div>
      <div className="sidebar-label">ESPACIO DE TRABAJO</div>
      <nav aria-label="Navegación principal">
        <button className={page==="mapa"?"active":""} onClick={()=>navigate("mapa")}><LayoutDashboard size={19}/>Vista territorial <ChevronRight size={15}/></button>
        <button className={page==="prediccion"?"active":""} onClick={()=>navigate("prediccion")}><Activity size={19}/>Consultar modelo</button>
        <button className={page==="planes"?"active":""} onClick={()=>navigate("planes")}><MapPinned size={19}/>Planificar brigadas</button>
        {user.role==="admin"&&<><div className="sidebar-label inner">ADMINISTRACIÓN</div><button className={page==="datos"?"active":""} onClick={()=>navigate("datos")}><Database size={19}/>Gestión de datos</button><button className={page==="laboratorio"?"active":""} onClick={()=>navigate("laboratorio")}><Activity size={19}/>Laboratorio IA</button><button className={page==="usuarios"?"active":""} onClick={()=>navigate("usuarios")}><Users size={19}/>Usuarios</button></>}
      </nav>
      <div className="sidebar-bottom"><div className="sidebar-note"><ShieldCheck size={19}/><p><strong>Apoyo a decisiones</strong><br/>Los resultados requieren revisión humana.</p></div><button className="profile" onClick={()=>request("/auth/logout",{method:"POST"}).finally(()=>setUser(null))}><span className="avatar">{user.username.slice(0,1).toUpperCase()}</span><span><strong>{user.username}</strong><small>{user.role==="admin"?"Administrador IA":"Usuario operativo"}</small></span><LogOut size={17}/></button></div>
    </aside>
    <main className="main">
      <header className="topbar"><button className="mobile-menu" onClick={()=>setMenu(!menu)} aria-label="Abrir menú"><Menu/></button><div className="breadcrumb">Plataforma <ChevronRight size={14}/> <strong>{page==="mapa"?"Vista territorial":page==="planes"?"Planificar brigadas":page==="prediccion"?"Consultar modelo":page==="datos"?"Gestión de datos":page==="laboratorio"?"Laboratorio IA":"Usuarios"}</strong></div><div className="top-right"><span className="status-dot"/> Sistema local <span className="top-divider"/> <CircleHelp size={18}/></div></header>
      <div className="content">
        {error&&<div className="alert" role="alert">{error}<button onClick={()=>setError("")} aria-label="Cerrar"><X size={16}/></button></div>}
        {message&&<div className="success" role="status"><Check size={16}/>{message}</div>}
        {page==="mapa"&&<>
          <div className="heading-row"><div><div className="overline"><span/> PANORAMA TERRITORIAL</div><h1>Decisiones que llegan más lejos.</h1><p>Explora la prioridad estimada y encuentra dónde orientar tus brigadas.</p></div><button className="primary" onClick={()=>navigate("planes")}><Plus size={17}/> Planificar brigadas</button></div>
          <div className="summary-strip">
            <div><span>Municipios analizados</span><strong>{num(items.length)}</strong><small>En el filtro seleccionado</small></div>
            <div><span>Prioridad alta estimada</span><strong>{num(items.filter(x=>x.probability>=.5&&x.es_hub!==1).length)}</strong><small>Umbral de referencia ≥ 50%</small></div>
            <div><span>Probabilidad promedio</span><strong>{items.length?pct(average):"—"}</strong><small>Salida del modelo activo</small></div>
            <div className="summary-context"><span>FUENTE DE ANÁLISIS</span><strong>{modelName}</strong><small>Datos de referencia · {year}</small></div>
          </div>
          <section className="workspace">
            <div className="section-top"><div><h2>Explorador territorial</h2><p>Selecciona un punto o un municipio de la lista para consultar su información.</p></div><div className="filters"><label><span>Departamento</span><select value={department} onChange={e=>setDepartment(e.target.value)}>{catalog.departments.map(d=><option key={d} value={d}>{departmentName(d)}</option>)}</select></label><label><span>Año</span><select value={year} onChange={e=>setYear(+e.target.value)}>{catalog.years.map(y=><option key={y}>{y}</option>)}</select></label></div></div>
            <div className="explorer"><div className="map-wrap"><MapView items={items} selected={selected} onSelect={setSelected} plan={plan}/><div className="map-label"><span className="live-dot"/> VISTA GEOGRÁFICA <small>Municipios por coordenadas</small></div><div className="legend"><span>Prioridad estimada</span><i className="dot low"/><small>Menor</small><i className="dot mid"/><i className="dot high"/><small>Mayor</small></div></div>
              <div className="detail"><div className="detail-head"><span>DETALLE MUNICIPAL</span><MapPinned size={17}/></div>{selected?<><h3>{selected.nom_mpio}</h3><p className="subtle">Código {selected.cod_mpio} · {selected.a_o}</p><div className="score"><span>Probabilidad estimada de prioridad alta</span><div><strong>{pct(selected.probability)}</strong><span className="tag">{selected.es_hub===1?"HUB":selected.probability>=.5?"ALTA":"REGULAR"}</span></div><div className="bar"><span style={{width:`${selected.probability*100}%`}}/></div><small>Salida del modelo, no diagnóstico clínico.</small></div><dl><div><dt>Población</dt><dd>{num(selected.poblacion)}</dd></div><div><dt>Rural disperso</dt><dd>{selected.pct_rural_disperso==null?"—":`${num(selected.pct_rural_disperso)}%`}</dd></div><div><dt>NBI rural</dt><dd>{selected.nbi_rural==null?"—":`${num(selected.nbi_rural)}%`}</dd></div><div><dt>Resguardos</dt><dd>{num(selected.n_resguardos)}</dd></div></dl>{selected.es_hub===1&&<p className="note">Municipio identificado como hub; se excluye de la asignación.</p>}</>:<p className="subtle">No hay municipios disponibles para este filtro.</p>}</div>
            </div>
            <div className="table-head"><div><h3>Municipios del territorio</h3><p>Ordenados por probabilidad estimada</p></div><span>{loading?"Cargando…":`${items.length} resultados`}</span></div>
            <div className="table-wrap"><table><thead><tr><th>Municipio</th><th>Población</th><th>Rural disperso</th><th>Probabilidad</th><th>Estado</th></tr></thead><tbody>{items.map(m=><tr key={m.cod_mpio} tabIndex={0} onClick={()=>setSelected(m)} onKeyDown={e=>{if(e.key==="Enter")setSelected(m)}} className={selected?.cod_mpio===m.cod_mpio?"selected-row":""}><td><strong>{m.nom_mpio}</strong><small>{m.cod_mpio}</small></td><td>{num(m.poblacion)}</td><td>{m.pct_rural_disperso==null?"—":`${num(m.pct_rural_disperso)}%`}</td><td><strong>{pct(m.probability)}</strong></td><td><span className="table-tag">{m.es_hub===1?"Hub":m.probability>=.5?"Prioridad alta":"Regular"}</span></td></tr>)}</tbody></table>{!loading&&!items.length&&<p className="empty">No se encontraron datos para esta selección.</p>}</div>
          </section><p className="footnote">Las probabilidades son estimaciones del modelo activo y no han sido calibradas. Los puntos son coordenadas municipales, no límites territoriales.</p>
        </>}
        {page==="laboratorio"&&user.role==="admin"&&<Laboratory request={request} json={json} onPublished={()=>setRevision(x=>x+1)}/>}
        {page==="prediccion"&&<Prediction key={`${department}-${year}-${revision}`} items={items} year={year} request={request} json={json}/>}
        {page==="planes"&&<><div className="heading-row"><div><div className="overline"><span/> PLANIFICACIÓN OPERATIVA</div><h1>Planea con perspectiva.</h1><p>Configura los recursos disponibles para obtener una propuesta de asignación.</p></div></div><div className="two-cols"><section className="panel"><div className="panel-title"><SlidersHorizontal/><div><h2>Configurar escenario</h2><p>La selección considera prioridad, población vulnerable y distancia.</p></div></div><div className="form-grid"><label>Departamento<select value={department} onChange={e=>setDepartment(e.target.value)}>{catalog.departments.map(d=><option key={d} value={d}>{departmentName(d)}</option>)}</select></label><label>Año<select value={year} onChange={e=>setYear(+e.target.value)}>{catalog.years.map(y=><option key={y}>{y}</option>)}</select></label><label>Brigadas disponibles<input type="number" min="1" max="100" value={brigades} onChange={e=>setBrigades(+e.target.value)}/></label><label>Distancia máxima (km)<input type="number" min="1" max="2000" value={distance} onChange={e=>setDistance(+e.target.value)}/></label><label>Destinos mínimos con resguardos<input type="number" min="0" value={minimum} onChange={e=>setMinimum(+e.target.value)}/></label></div><div className="info-box"><MapPinned size={19}/><div><strong>Base: Valledupar</strong><p>10.460472, -73.259398 · La distancia es geográfica de ida (Haversine), no una ruta por carretera.</p></div></div><button className="primary full" disabled={loading} onClick={runPlan}>{loading?"Calculando…":"Generar propuesta"} <ArrowRight size={17}/></button></section><section className="panel side-explainer"><span className="panel-icon"><Activity/></span><h2>Una propuesta, no una orden.</h2><p>El modelo identifica patrones en datos históricos. El optimizador combina esa señal con restricciones para proponer municipios candidatos.</p><ul><li>Los hubs se excluyen de la asignación.</li><li>Las restricciones no se relajan automáticamente.</li><li>La decisión final requiere revisión en territorio.</li></ul></section></div></>}
        {page==="datos"&&<><div className="heading-row"><div><div className="overline"><span/> LABORATORIO DE DATOS</div><h1>Datos que dan contexto.</h1><p>Revisa los datos históricos y registra información adicional de Colombia.</p></div></div><div className="summary-strip admin-stats"><div><span>Registros históricos</span><strong>{num(stats?.records)}</strong><small>Municipio · año</small></div><div><span>Municipios</span><strong>{num(stats?.municipalities)}</strong><small>En dataset histórico</small></div><div><span>Datos faltantes</span><strong>{stats?`${stats.missing_percent}%`:"—"}</strong><small>De las celdas históricas</small></div><div><span>Registros adicionales</span><strong>{num(stats?.added_records)}</strong><small>Almacenados por separado</small></div></div><div className="two-cols"><section className="panel"><div className="panel-title"><FileUp/><div><h2>Importar CSV</h2><p>Columnas mínimas: cod_mpio, nom_mpio, a_o, poblacion.</p></div></div><div className="info-box"><CircleHelp size={18}/><p>La carga guarda filas válidas de inmediato y muestra las rechazadas. No modifica el dataset histórico ni el modelo.</p></div><label className="file-picker"><input type="file" accept=".csv,text/csv" onChange={e=>setUpload(e.target.files?.[0]??null)}/><FileUp size={25}/><strong>{upload?.name??"Selecciona un archivo CSV"}</strong><small>UTF-8 · máximo 2 MB</small></label><button className="primary full" disabled={!upload} onClick={async()=>{if(!upload)return;const form=new FormData();form.append("file",upload);try{setImportResult(await request("/imports",{method:"POST",body:form}));setError("")}catch(e){setError((e as Error).message)}}}>Importar registros <ArrowRight size={16}/></button>{importResult&&<div className="import-result"><strong>{importResult.accepted} aceptados · {importResult.rejected.length} rechazados</strong>{importResult.rejected.slice(0,10).map((r:any)=><p key={r.fila}>Fila {r.fila}: {r.errores.join(" ")}</p>)}</div>}</section><section className="panel"><div className="panel-title"><Plus/><div><h2>Registro individual</h2><p>Agrega un municipio y año a los registros adicionales.</p></div></div><div className="form-grid">{Object.entries({cod_mpio:"Código DIVIPOLA",nom_mpio:"Municipio",a_o:"Año",poblacion:"Población"}).map(([key,label])=><label key={key}>{label}<input value={record[key as keyof typeof record]} onChange={e=>setRecord({...record,[key]:e.target.value})} placeholder={key==="cod_mpio"?"Ej. 20011":""}/></label>)}</div><button className="secondary full" onClick={async()=>{try{await request("/records",json(record));setMessage("Registro adicional guardado.");setRecord({cod_mpio:"",nom_mpio:"",a_o:"2022",poblacion:""})}catch(e){setError((e as Error).message)}}}>Guardar registro <ArrowRight size={16}/></button><p className="footnote">Los registros adicionales aún no se incorporan al entrenamiento.</p></section></div></>}
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
