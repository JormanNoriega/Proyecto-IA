import {useEffect, useState, type RefObject} from "react";
import * as maplibregl from "maplibre-gl";

export function useMunicipalityOutline(map:RefObject<maplibregl.Map|null>, code:string, request:(path:string, options?:RequestInit)=>Promise<any>, zoom=false) {
  const [error,setError]=useState("");
  useEffect(()=>{
    const m=map.current;
    if(!m)return;
    let active=true;
    const clear=()=>{
      if(m.getLayer("municipality-outline"))m.removeLayer("municipality-outline");
      if(m.getSource("municipality-outline"))m.removeSource("municipality-outline");
    };
    if(m.getStyle())clear();
    setError("");
    if(!code)return ()=>{active=false};
    request(`/geography/municipalities/${encodeURIComponent(code)}`).then(feature=>{
      if(!active)return;
      const draw=()=>{
        if(!active)return;
        clear();
        m.addSource("municipality-outline",{type:"geojson",data:feature});
        m.addLayer({id:"municipality-outline",type:"line",source:"municipality-outline",paint:{"line-color":"#b15c22","line-width":3}});
        if(zoom){
          const bounds=new maplibregl.LngLatBounds();
          const visit=(coords:any)=>{
            if(typeof coords[0]==="number")bounds.extend([coords[0],coords[1]]);
            else coords.forEach(visit);
          };
          visit(feature.geometry.coordinates);
          if(!bounds.isEmpty())m.fitBounds(bounds,{padding:40,maxZoom:10,duration:600});
        }
      };
      if(m.isStyleLoaded())draw();else m.once("idle",draw);
    }).catch(()=>{if(active)setError("No se pudo mostrar el contorno del municipio seleccionado.")});
    return ()=>{active=false};
  },[map,code,request,zoom]);
  return error;
}
