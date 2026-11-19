import React, {useEffect, useRef, useState} from "react";
import * as maplibregl from "maplibre-gl";
import {useDepartmentOutline} from "./useDepartmentOutline";
import {useMunicipalityOutline} from "./useMunicipalityOutline";

type Territory = {code:string; name:string; kind?:string};
type Base = {id:number; name:string; municipality_code:string; municipality:string; department:string; latitude:number; longitude:number; coordinate_source:string; nit:string|null; address:string|null; phone:string|null; contact_name:string|null; geo_status:string; geo_review?:{message:string}};

const emptyForm = {name:"",municipality_code:"",latitude:"",longitude:"",coordinate_source:"",coordinates_confirmed:false,nit:"",address:"",phone:"",contact_name:""};

function BaseMap({latitude,longitude,onPick,department,municipality,request}:{latitude:string; longitude:string; onPick:(lat:number,lon:number)=>void; department:string; municipality:string; request:(path:string, options?:RequestInit)=>Promise<any>}) {
  const container=useRef<HTMLDivElement>(null);
  const map=useRef<maplibregl.Map|null>(null);
  const marker=useRef<maplibregl.Marker|null>(null);
  const onPickRef=useRef(onPick);
  const [mapError,setMapError]=useState(false);
  onPickRef.current=onPick;
  useEffect(()=>{
    if(!container.current)return;
    const m=new maplibregl.Map({container:container.current,style:"https://tiles.openfreemap.org/styles/positron",center:[-74.3,4.6],zoom:4.4});
    let errors=0;
    m.addControl(new maplibregl.NavigationControl({showCompass:false}),"top-right");
    m.on("error",()=>{if(++errors>=3)setMapError(true)});
    m.on("click",e=>onPickRef.current(e.lngLat.lat,((e.lngLat.lng+180)%360+360)%360-180));
    map.current=m;
    return ()=>{marker.current?.remove();marker.current=null;m.remove();map.current=null};
  },[]);
  const outlineError=useDepartmentOutline(map,department,request,!municipality);
  const municipalityOutlineError=useMunicipalityOutline(map,municipality.startsWith(department)?municipality:"",request,true);
  useEffect(()=>{
    const lat=Number(latitude),lon=Number(longitude);
    if(!map.current||!latitude.trim()||!longitude.trim()||!Number.isFinite(lat)||!Number.isFinite(lon)||Math.abs(lat)>90||Math.abs(lon)>180){
      marker.current?.remove();marker.current=null;return;
    }
    if(!marker.current)marker.current=new maplibregl.Marker({color:"#315e54"}).setLngLat([lon,lat]).addTo(map.current);
    else marker.current.setLngLat([lon,lat]);
  },[latitude,longitude]);
  return <><div ref={container} className="base-map" role="region" aria-label="Mapa para seleccionar la ubicación de la base. También puedes escribir las coordenadas en el formulario."/>
    {mapError&&<p className="base-map-warning" role="status">Algunos recursos del mapa no cargaron. Revisa la conexión o introduce las coordenadas manualmente.</p>}
    {outlineError&&<p className="base-map-warning" role="status">{outlineError}</p>}
    {municipalityOutlineError&&<p className="base-map-warning" role="status">{municipalityOutlineError}</p>}
  </>;
}

export default function Bases({request, json}:{request:(path:string, options?:RequestInit)=>Promise<any>; json:(body:unknown)=>RequestInit}) {
  const [departments,setDepartments]=useState<Territory[]>([]);
  const [municipalities,setMunicipalities]=useState<Territory[]>([]);
  const [bases,setBases]=useState<Base[]>([]);
  const [department,setDepartment]=useState("20");
  const [form,setForm]=useState(emptyForm);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const [busy,setBusy]=useState(false);
  const [validation,setValidation]=useState<{status:string;message:string}|null>(null);
  const [validating,setValidating]=useState(false);
  const [validationAttempt,setValidationAttempt]=useState(0);
  const visibleBases=bases.filter(b=>b.municipality_code===form.municipality_code);
  const reload=()=>request("/bases").then(setBases);
  useEffect(()=>{request("/territories").then(data=>setDepartments(data.departments)).catch(e=>setError(e.message));reload().catch(e=>setError(e.message))},[]);
  useEffect(()=>{
    let active=true;
    setMunicipalities([]);
    setForm(f=>({...f,municipality_code:"",coordinates_confirmed:false}));
    request(`/territories?department=${department}`).then(data=>{if(active)setMunicipalities(data.items)}).catch(e=>{if(active)setError(e.message)});
    return ()=>{active=false};
  },[department]);
  useEffect(()=>{
    let active=true;
    const controller=new AbortController();
    setValidation(null);
    setValidating(false);
    if(!form.municipality_code||!form.latitude.trim()||!form.longitude.trim())return;
    const lat=Number(form.latitude),lon=Number(form.longitude);
    if(!Number.isFinite(lat)||!Number.isFinite(lon)||Math.abs(lat)>90||Math.abs(lon)>180){
      setValidation({status:"RANGO_INVALIDO",message:"Las coordenadas están fuera del rango permitido: latitud entre −90 y 90, longitud entre −180 y 180."});
      return;
    }
    setValidating(true);
    const timer=window.setTimeout(()=>request("/geography/validate",{...json({municipality_code:form.municipality_code,latitude:lat,longitude:lon}),signal:controller.signal})
      .then(result=>{if(active)setValidation(result)}).catch((error:unknown)=>{if(active)setValidation({status:"ERROR",message:`No se pudo comprobar la ubicación: ${error instanceof Error ? error.message : "error de conexión"}.`})}).finally(()=>{if(active)setValidating(false)}),400);
    return ()=>{active=false;window.clearTimeout(timer);controller.abort()};
  },[form.municipality_code,form.latitude,form.longitude,validationAttempt]);
  async function save(e:React.FormEvent) {
    e.preventDefault(); setError(""); setMessage(""); setBusy(true);
    try {
      await request("/bases",json({...form,latitude:Number(form.latitude),longitude:Number(form.longitude)}));
      setForm({...emptyForm,municipality_code:form.municipality_code});
      await reload(); setMessage("Base registrada. Su disponibilidad se definirá en cada jornada.");
    } catch(e) {setError((e as Error).message)} finally {setBusy(false)}
  }
  return <>
    <div className="heading-row"><div><h1>Bases operativas</h1><p>Registra los puntos desde los que podrían salir las brigadas.</p></div></div>
    {error&&<div className="alert" role="alert">{error}</div>}
    {message&&<div className="success" role="status">{message}</div>}
    <div className="two-cols">
      <form className="panel" onSubmit={save}>
        <div className="panel-title"><div><h2>Registrar una base</h2><p>Introduce una ubicación verificada; el municipio no necesita tener datos de IA.</p></div></div>
        <div className="form-grid">
          <label>Nombre de la base<input required maxLength={160} value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></label>
          <label>Departamento<select value={department} onChange={e=>setDepartment(e.target.value)}>{departments.map(d=><option key={d.code} value={d.code}>{d.name}</option>)}</select></label>
          <label>Municipio<select required value={form.municipality_code} onChange={e=>setForm({...form,municipality_code:e.target.value,coordinates_confirmed:false})}><option value="">Selecciona un municipio</option>{municipalities.map(m=><option key={m.code} value={m.code}>{m.name} · {m.code}{m.kind && m.kind!=="Municipio"?` (${m.kind})`:""}</option>)}</select></label>
          <label>Latitud<input required type="number" step="any" min="-90" max="90" aria-describedby="location-validation" aria-invalid={validation?.status==="FUERA_DE_DEPARTAMENTO"||validation?.status==="FUERA_DE_MUNICIPIO"||validation?.status==="RANGO_INVALIDO"} value={form.latitude} onChange={e=>setForm({...form,latitude:e.target.value,coordinates_confirmed:false})}/></label>
          <label>Longitud<input required type="number" step="any" min="-180" max="180" aria-describedby="location-validation" aria-invalid={validation?.status==="FUERA_DE_DEPARTAMENTO"||validation?.status==="FUERA_DE_MUNICIPIO"||validation?.status==="RANGO_INVALIDO"} value={form.longitude} onChange={e=>setForm({...form,longitude:e.target.value,coordinates_confirmed:false})}/></label>
          <label>Fuente de coordenadas<input required maxLength={200} value={form.coordinate_source} onChange={e=>setForm({...form,coordinate_source:e.target.value})} placeholder="Ej. verificación en terreno"/></label>
        </div>
        <div className="lab-heading"><h2>Información de contacto <span className="subtle">(opcional)</span></h2><p>Usa datos institucionales o autorizados; serán visibles para los usuarios de la aplicación.</p></div>
        <div className="form-grid">
          <label>NIT de la institución<input maxLength={30} value={form.nit} onChange={e=>setForm({...form,nit:e.target.value})} placeholder="Incluye dígito de verificación si aplica"/></label>
          <label>Dirección<input maxLength={200} value={form.address} onChange={e=>setForm({...form,address:e.target.value})}/></label>
          <label>Teléfono de contacto<input type="tel" maxLength={40} value={form.phone} onChange={e=>setForm({...form,phone:e.target.value})}/></label>
          <label>Responsable o contacto<input maxLength={160} value={form.contact_name} onChange={e=>setForm({...form,contact_name:e.target.value})}/></label>
        </div>
        <div id="location-validation" className={`location-status ${validation?.status==="VALIDADA"?"location-status-valid":validation?"location-status-warning":""}`} role="status" aria-live="polite">
          <strong>{validating?"Comprobando ubicación…":validation?.status==="VALIDADA"?"Ubicación verificada":validation?"No se puede guardar esta ubicación":"Ubicación pendiente"}</strong>
          <p>{validating?"Consultando los límites departamental y municipal.":validation?validation.message:"Selecciona municipio y coordenadas para comprobar la ubicación con el MGN 2025."}</p>
          {validation?.status==="ERROR"?<button type="button" onClick={()=>setValidationAttempt(n=>n+1)}>Reintentar comprobación</button>:validation&&validation.status!=="VALIDADA"&&<p>Revisa el municipio o selecciona otro punto; si falta la geometría o está cerca del límite, solicita revisión.</p>}
        </div>
        <label><input type="checkbox" required checked={form.coordinates_confirmed} onChange={e=>setForm({...form,coordinates_confirmed:e.target.checked})}/> Confirmo que revisé la ubicación de esta base.</label>
        <div className="lab-actions"><button className="primary" disabled={busy||validating||validation?.status!=="VALIDADA"}>{busy?"Guardando…":"Guardar base"}</button></div>
      </form>
      <div className="base-side">
        <section className="panel"><h2>Ubicación de la base</h2><p className="subtle">Acércate y haz clic en el mapa para completar las coordenadas. También puedes escribirlas a la izquierda.</p>
          <BaseMap department={department} municipality={form.municipality_code} request={request} latitude={form.latitude} longitude={form.longitude} onPick={(lat,lon)=>setForm(f=>({...f,latitude:lat.toFixed(6),longitude:lon.toFixed(6),coordinate_source:f.coordinate_source||"Selección manual en mapa OpenFreeMap",coordinates_confirmed:false}))}/>
          {validation&&validation.status!=="VALIDADA"&&<div className="location-status location-status-warning" role="status"><strong>Revisa el punto seleccionado</strong><p>{validation.message}</p></div>}
          <p className="footnote">Verde: departamento. Naranja: municipio seleccionado. Los contornos son simplificados; la comprobación usa la geometría original del MGN, que no certifica límites jurídicos.</p>
        </section>
        <section className="panel"><h2>Bases del municipio seleccionado</h2><p className="subtle">Registrar una base no confirma brigadas disponibles.</p>
          {!form.municipality_code?<p className="empty">Selecciona un municipio para consultar sus bases.</p>:!visibleBases.length?<p className="empty">No hay bases registradas en este municipio.</p>:<div className="version-list">{visibleBases.map(b=><div key={b.id}><span><strong>{b.name}</strong><small>{b.municipality}, {b.department}<br/>{b.latitude}, {b.longitude} · {b.coordinate_source}<br/>Estado: {b.geo_status}{b.geo_review&&<> · Revisión actual: {b.geo_review.message}</>}{b.address&&<><br/>Dirección: {b.address}</>}{b.nit&&<><br/>NIT: {b.nit}</>}{b.phone&&<><br/>Teléfono: {b.phone}</>}{b.contact_name&&<><br/>Contacto: {b.contact_name}</>}</small></span></div>)}</div>}
        </section>
      </div>
    </div>
  </>;
}
