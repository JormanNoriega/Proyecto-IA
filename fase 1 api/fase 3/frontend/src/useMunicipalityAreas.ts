import {useEffect, useRef, useState, type RefObject} from "react";
import * as maplibregl from "maplibre-gl";

export function useMunicipalityAreas(map:RefObject<maplibregl.Map|null>, department:string, selectedCode:string, onPick:(code:string)=>void) {
  const pickRef=useRef(onPick);
  pickRef.current=onPick;
  const selectedRef=useRef(selectedCode);
  selectedRef.current=selectedCode;
  const popupRef=useRef<maplibregl.Popup|null>(null);
  const hoveredCodeRef=useRef("");
  useEffect(()=>{
    const m=map.current;
    if(hoveredCodeRef.current===selectedCode)popupRef.current?.remove();
    if(m?.getLayer("municipality-areas-fill")) {
      m.setPaintProperty("municipality-areas-fill","fill-opacity",["case",["==",["get","code"],selectedCode],0.07,["boolean",["feature-state","hover"],false],0.3,0.07]);
    }
  },[map,selectedCode]);
  const [error,setError]=useState("");
  useEffect(()=>{
    const m=map.current;
    if(!m)return;
    let active=true;
    let hovered:string|number|null=null;
    const popup=new maplibregl.Popup({closeButton:false,closeOnClick:false,offset:12});
    popupRef.current=popup;
    const move=(e:maplibregl.MapLayerMouseEvent)=>{
      const feature=e.features?.[0];
      if(!feature)return;
      if(hovered!==null)m.setFeatureState({source:"municipality-areas",id:hovered},{hover:false});
      hovered=feature.id??null;
      if(hovered!==null)m.setFeatureState({source:"municipality-areas",id:hovered},{hover:true});
      m.getCanvas().style.cursor="pointer";
      hoveredCodeRef.current=String(feature.properties?.code ?? "");
      if(hoveredCodeRef.current===selectedRef.current)popup.remove();
      else popup.setLngLat(e.lngLat).setText(`${feature.properties?.name ?? "Municipio"} · ${hoveredCodeRef.current}`).addTo(m);
    };
    const leave=()=>{
      if(hovered!==null&&m.getSource("municipality-areas"))m.setFeatureState({source:"municipality-areas",id:hovered},{hover:false});
      hovered=null;hoveredCodeRef.current="";m.getCanvas().style.cursor="";popup.remove();
    };
    const click=(e:maplibregl.MapLayerMouseEvent)=>{const code=e.features?.[0]?.properties?.code;if(code)pickRef.current(String(code))};
    const clear=()=>{
      popup.remove();
      if(m.getLayer("municipality-areas-fill")) {
        m.off("mousemove","municipality-areas-fill",move);
        m.off("mouseleave","municipality-areas-fill",leave);
        m.off("click","municipality-areas-fill",click);
        m.removeLayer("municipality-areas-fill");
      }
      if(m.getLayer("municipality-areas-lines"))m.removeLayer("municipality-areas-lines");
      if(m.getSource("municipality-areas"))m.removeSource("municipality-areas");
    };
    if(m.getStyle())clear();
    setError("");
    fetch(`/api/v1/geography/departments/${encodeURIComponent(department)}/municipalities`,{credentials:"include"})
      .then(response=>{if(!response.ok)throw new Error();return response.json()})
      .then(data=>{
        if(!active)return;
        const draw=()=>{
          if(!active)return;
          clear();
          m.addSource("municipality-areas",{type:"geojson",data,promoteId:"code"});
          m.addLayer({id:"municipality-areas-fill",type:"fill",source:"municipality-areas",paint:{"fill-color":"#40816a","fill-opacity":["case",["==",["get","code"],selectedRef.current],0.07,["boolean",["feature-state","hover"],false],0.3,0.07]}});
          m.addLayer({id:"municipality-areas-lines",type:"line",source:"municipality-areas",paint:{"line-color":"#447663","line-width":1,"line-opacity":0.8}});
          if(m.getLayer("municipality-outline"))m.moveLayer("municipality-outline");
          m.on("mousemove","municipality-areas-fill",move);
          m.on("mouseleave","municipality-areas-fill",leave);
          m.on("click","municipality-areas-fill",click);
        };
        if(m.isStyleLoaded())draw();else m.once("idle",draw);
      }).catch(()=>{if(active)setError("No se pudieron cargar las figuras municipales. Puedes usar la lista para seleccionar.")});
    return ()=>{active=false;hoveredCodeRef.current="";popupRef.current=null;if(m.getStyle())clear()};
  },[map,department]);
  return error;
}
