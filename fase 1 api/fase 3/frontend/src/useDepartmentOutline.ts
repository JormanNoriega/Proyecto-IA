import {useEffect, useRef, useState, type RefObject} from "react";
import * as maplibregl from "maplibre-gl";

export function useDepartmentOutline(map:RefObject<maplibregl.Map|null>, department:string, request:(path:string, options?:RequestInit)=>Promise<any>, fit=true) {
  const [error,setError]=useState("");
  const fitRef=useRef(fit);
  fitRef.current=fit;
  useEffect(()=>{
    const m=map.current;
    if(!m)return;
    let active=true;
    const clear=()=>{
      if(m.getLayer("department-outline"))m.removeLayer("department-outline");
      if(m.getSource("department-outline"))m.removeSource("department-outline");
    };
    if(m.getStyle())clear();
    setError("");
    request(`/geography/departments/${department}`).then(feature=>{
      if(!active)return;
      const draw=()=>{
        if(!active)return;
        clear();
        m.addSource("department-outline",{type:"geojson",data:feature});
        m.addLayer({id:"department-outline",type:"line",source:"department-outline",paint:{"line-color":"#315e54","line-width":2.5}});
        const bounds=new maplibregl.LngLatBounds();
        const visit=(coords:any)=>{
          if(typeof coords[0]==="number")bounds.extend([coords[0],coords[1]]);
          else coords.forEach(visit);
        };
        visit(feature.geometry.coordinates);
        if(fitRef.current&&!bounds.isEmpty())m.fitBounds(bounds,{padding:40,maxZoom:9,duration:600});
      };
      if(m.isStyleLoaded())draw(); else m.once("idle",draw);
    }).catch(()=>{if(active)setError("No está disponible el contorno del departamento.")});
    return ()=>{active=false};
  },[map,department,request]);
  return error;
}
