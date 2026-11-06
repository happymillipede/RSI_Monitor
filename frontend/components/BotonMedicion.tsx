// Botón grande Encender / Apagar y las opciones de la medición.
// - Modo: BITalino real o Simulación (en Docker solo hay simulación).
// - En simulación: escenario (normal / fatigue_test), velocidad y si se usan los
//   umbrales de prueba SIM_* del original. El backend recuerda lo elegido.
// Qué se puede editar aquí: los textos. Las velocidades salen de config.json.

"use client";

import { useState } from "react";
import type { Escenario, InfoMedicion, Modo, PedidoEncender } from "@/lib/tipos";
import estilos from "./BotonMedicion.module.css";

interface Props {
  medicion: InfoMedicion;
  enDocker: boolean;
  velocidades: number[];
  umbralesSimGuardado: boolean;
  ocupado: boolean;
  alEncender: (pedido: PedidoEncender) => void;
  alApagar: () => void;
}

const NOMBRES_MODO: Record<Modo, string> = { real: "BITalino", simulacion: "Simulación" };
const ESCENARIOS: Escenario[] = ["normal", "fatigue_test"];

export default function BotonMedicion(props: Props) {
  const { medicion, enDocker, velocidades, ocupado } = props;
  const [modo, setModo] = useState<Modo>(enDocker ? "simulacion" : medicion.modo_preferido);
  const [escenario, setEscenario] = useState<Escenario>(medicion.escenario ?? "fatigue_test");
  const [velocidad, setVelocidad] = useState<number>(medicion.velocidad || velocidades[0]);
  const [umbralesSim, setUmbralesSim] = useState(props.umbralesSimGuardado);

  function encender() {
    if (modo === "real") {
      props.alEncender({ modo });
    } else {
      props.alEncender({ modo, escenario, velocidad, umbrales_sim: umbralesSim });
    }
  }

  if (medicion.encendida) {
    return (
      <section className="tarjeta">
        <h2>Medición</h2>
        <button className={`${estilos.boton} ${estilos.apagar}`} onClick={props.alApagar} disabled={ocupado}>
          Apagar
        </button>
        <p className={estilos.detalle}>
          {medicion.modo ? NOMBRES_MODO[medicion.modo] : ""}
          {medicion.modo === "simulacion" &&
            ` · ${medicion.escenario} · ×${medicion.velocidad}${medicion.umbrales_sim ? " · umbrales SIM_*" : ""}`}
        </p>
      </section>
    );
  }

  return (
    <section className="tarjeta">
      <h2>Medición</h2>
      <button className={`${estilos.boton} ${estilos.encender}`} onClick={encender} disabled={ocupado}>
        Encender
      </button>

      <div className={estilos.opciones}>
        <label>
          Modo{" "}
          <select value={modo} onChange={(e) => setModo(e.target.value as Modo)}>
            <option value="real" disabled={enDocker}>
              {NOMBRES_MODO.real}
            </option>
            <option value="simulacion">{NOMBRES_MODO.simulacion}</option>
          </select>
        </label>

        {modo === "simulacion" && (
          <>
            <label>
              Escenario{" "}
              <select value={escenario} onChange={(e) => setEscenario(e.target.value as Escenario)}>
                {ESCENARIOS.map((nombre) => (
                  <option key={nombre} value={nombre}>
                    {nombre}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Velocidad{" "}
              <select value={velocidad} onChange={(e) => setVelocidad(Number(e.target.value))}>
                {velocidades.map((valor) => (
                  <option key={valor} value={valor}>
                    ×{valor}
                  </option>
                ))}
              </select>
            </label>
            <label className={estilos.casilla}>
              <input type="checkbox" checked={umbralesSim} onChange={(e) => setUmbralesSim(e.target.checked)} />
              Umbrales de prueba (SIM_* del original)
            </label>
            {escenario === "fatigue_test" && !umbralesSim && (
              <p className={estilos.nota}>
                Con los umbrales normales, fatigue_test no llega a dar la alerta (el RMS sube solo cerca de 3 %).
              </p>
            )}
          </>
        )}
      </div>
    </section>
  );
}
