// Descansos: tomar un descanso a mano, plantillas e historial.
// - "Tomar descanso": con una plantilla guardada (ej. "Café, 15 min") o con una duración libre.
// - Plantillas: crear, editar y borrar (quedan guardadas en datos/descansos.json).
// - Historial: los descansos guardados y el total de hoy.
// El descanso por fatiga empieza al apretar Aceptar en la alerta (AlertaFatiga.tsx).
// Qué se puede editar aquí: los textos y MAXIMO_HISTORIAL.

"use client";

import { useEffect, useState } from "react";
import * as api from "@/lib/api";
import { horaDe, minutosTexto } from "@/lib/formato";
import type { PedidoDescanso, Plantilla, RespuestaHistorial } from "@/lib/tipos";
import estilos from "./Descansos.module.css";

const MAXIMO_HISTORIAL = 20; // cuántos descansos se muestran
const DURACION_LIBRE = -1; // valor del selector para "duración libre"
const MINUTOS_LIBRES_INICIALES = 5;
const NOMBRES_ORIGEN = { fatiga: "por fatiga", manual: "manual" };

interface Props {
  bloqueado: boolean; // hay una alerta pendiente o un descanso en curso
  ocupado: boolean;
  actualizacion: number; // cambia cuando termina un descanso: se vuelve a leer el historial
  alIniciar: (pedido: PedidoDescanso) => void;
  alError: (mensaje: string) => void;
}

export default function Descansos({ bloqueado, ocupado, actualizacion, alIniciar, alError }: Props) {
  const [plantillas, setPlantillas] = useState<Plantilla[]>([]);
  const [historial, setHistorial] = useState<RespuestaHistorial | null>(null);

  useEffect(() => {
    api.listarPlantillas().then((r) => setPlantillas(r.plantillas), (e: Error) => alError(e.message));
  }, [alError]);

  useEffect(() => {
    api.leerHistorial().then(setHistorial, (e: Error) => alError(e.message));
  }, [actualizacion, alError]);

  // Guarda un cambio en las plantillas y muestra la lista nueva que devuelve el backend.
  async function cambiarPlantillas(accion: () => Promise<{ plantillas: Plantilla[] }>) {
    try {
      setPlantillas((await accion()).plantillas);
      return true;
    } catch (e) {
      alError((e as Error).message);
      return false;
    }
  }

  return (
    <section className={`tarjeta ${estilos.descansos}`}>
      <h2>Descansos</h2>
      <TomarDescanso plantillas={plantillas} deshabilitado={bloqueado || ocupado} alIniciar={alIniciar} />
      <ListaPlantillas plantillas={plantillas} alCambiar={cambiarPlantillas} />
      {historial && <Historial historial={historial} />}
    </section>
  );
}

function TomarDescanso(props: { plantillas: Plantilla[]; deshabilitado: boolean; alIniciar: Props["alIniciar"] }) {
  const [eleccion, setEleccion] = useState(0);
  const [minutos, setMinutos] = useState(MINUTOS_LIBRES_INICIALES);
  const libre = eleccion === DURACION_LIBRE || props.plantillas.length === 0;

  return (
    <div className={estilos.bloque}>
      <h3>Tomar descanso</h3>
      <div className={estilos.fila}>
        <select value={libre ? DURACION_LIBRE : eleccion} onChange={(e) => setEleccion(Number(e.target.value))}>
          {props.plantillas.map((plantilla, indice) => (
            <option key={plantilla.nombre} value={indice}>
              {plantilla.nombre}, {minutosTexto(plantilla.duracion_min)} min
            </option>
          ))}
          <option value={DURACION_LIBRE}>Duración libre</option>
        </select>
        {libre && (
          <label>
            <input
              type="number"
              min={1}
              className={estilos.minutos}
              value={minutos}
              onChange={(e) => setMinutos(Number(e.target.value))}
            />{" "}
            min
          </label>
        )}
        <button
          disabled={props.deshabilitado}
          onClick={() => props.alIniciar(libre ? { minutos } : { plantilla: eleccion })}
        >
          Tomar descanso
        </button>
      </div>
    </div>
  );
}

interface PropsPlantillas {
  plantillas: Plantilla[];
  alCambiar: (accion: () => Promise<{ plantillas: Plantilla[] }>) => Promise<boolean>;
}

function ListaPlantillas({ plantillas, alCambiar }: PropsPlantillas) {
  const [editando, setEditando] = useState<number | null>(null);
  const [nueva, setNueva] = useState<Plantilla>({ nombre: "", duracion_min: MINUTOS_LIBRES_INICIALES });

  async function agregar() {
    if (await alCambiar(() => api.crearPlantilla(nueva))) {
      setNueva({ nombre: "", duracion_min: MINUTOS_LIBRES_INICIALES });
    }
  }

  return (
    <div className={estilos.bloque}>
      <h3>Plantillas</h3>
      <ul className={estilos.lista}>
        {plantillas.map((plantilla, indice) =>
          editando === indice ? (
            <li key={plantilla.nombre}>
              <EditarPlantilla
                inicial={plantilla}
                alGuardar={async (cambiada) => {
                  if (await alCambiar(() => api.editarPlantilla(indice, cambiada))) setEditando(null);
                }}
                alCancelar={() => setEditando(null)}
              />
            </li>
          ) : (
            <li key={plantilla.nombre} className={estilos.fila}>
              <span className={estilos.nombre}>
                {plantilla.nombre}, {minutosTexto(plantilla.duracion_min)} min
              </span>
              <button onClick={() => setEditando(indice)}>Editar</button>
              <button onClick={() => alCambiar(() => api.borrarPlantilla(indice))}>Borrar</button>
            </li>
          ),
        )}
      </ul>
      <div className={estilos.fila}>
        <input
          placeholder="Nombre (ej. Café)"
          value={nueva.nombre}
          onChange={(e) => setNueva({ ...nueva, nombre: e.target.value })}
        />
        <input
          type="number"
          min={1}
          className={estilos.minutos}
          value={nueva.duracion_min}
          onChange={(e) => setNueva({ ...nueva, duracion_min: Number(e.target.value) })}
        />{" "}
        min
        <button onClick={agregar}>Agregar</button>
      </div>
    </div>
  );
}

function EditarPlantilla(props: { inicial: Plantilla; alGuardar: (p: Plantilla) => void; alCancelar: () => void }) {
  const [plantilla, setPlantilla] = useState(props.inicial);
  return (
    <div className={estilos.fila}>
      <input value={plantilla.nombre} onChange={(e) => setPlantilla({ ...plantilla, nombre: e.target.value })} />
      <input
        type="number"
        min={1}
        className={estilos.minutos}
        value={plantilla.duracion_min}
        onChange={(e) => setPlantilla({ ...plantilla, duracion_min: Number(e.target.value) })}
      />{" "}
      min
      <button onClick={() => props.alGuardar(plantilla)}>Guardar</button>
      <button onClick={props.alCancelar}>Cancelar</button>
    </div>
  );
}

function Historial({ historial }: { historial: RespuestaHistorial }) {
  return (
    <div className={estilos.bloque}>
      <h3>Historial</h3>
      <p className={estilos.total}>
        Hoy: {historial.cantidad_hoy} {historial.cantidad_hoy === 1 ? "descanso" : "descansos"},{" "}
        {minutosTexto(historial.minutos_hoy)} min en total.
      </p>
      {historial.historial.length === 0 ? (
        <p className={estilos.vacio}>Todavía no hay descansos.</p>
      ) : (
        <table className={estilos.tabla}>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Hora</th>
              <th>Descanso</th>
              <th>Origen</th>
              <th>Planeado</th>
              <th>Real</th>
              <th>Completo</th>
            </tr>
          </thead>
          <tbody>
            {historial.historial.slice(0, MAXIMO_HISTORIAL).map((registro, indice) => (
              <tr key={`${indice}-${registro.inicio}`}>
                <td>{registro.inicio.slice(0, 10)}</td>
                <td>
                  {horaDe(registro.inicio)}–{horaDe(registro.fin)}
                </td>
                <td>{registro.nombre}</td>
                <td>{NOMBRES_ORIGEN[registro.origen]}</td>
                <td>{minutosTexto(registro.duracion_planeada_min)} min</td>
                <td>{minutosTexto(registro.duracion_real_min)} min</td>
                <td>{registro.completado ? "Sí" : "No (terminado antes)"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
