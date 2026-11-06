"""
Textos que ve el usuario y que salen del backend, para que el frontend solo los muestre.

- texto_panel(): réplica de actualizar_panel_adquisicion() del original (líneas 334-375).
  Dos cambios, porque la medición ya no dura DURACION = 120 s:
  "Duración configurada" dice "indefinida (hasta Apagar)" y "Muestras recibidas" va sin total.
- texto_alerta(): el texto exacto de la ventana de alerta de fatiga.
- texto_calibracion(), texto_linea_base(): mensajes del panel en tiempo real.

Qué se puede editar aquí: los textos (no el formato del panel, que copia al original).
"""

LARGO_MAXIMO_TRAMA = 160  # líneas 344-345 del original

TEXTO_ALERTA = "Riesgo de fatiga muscular, descanse {minutos} minutos"


def texto_panel(info, constantes, parametros, estado):
    """Texto del panel de información. Réplica de actualizar_panel_adquisicion() (líneas 334-375)."""
    if info.muestras_recientes:
        texto_muestras = "\n".join(
            f"  t={tiempo:8.3f} s | EMG={valor}" for tiempo, valor in info.muestras_recientes
        )
    else:
        texto_muestras = "  Todavía no hay muestras."

    texto_trama = repr(info.ultima_trama)
    if len(texto_trama) > LARGO_MAXIMO_TRAMA:
        texto_trama = texto_trama[: LARGO_MAXIMO_TRAMA - 3] + "..."

    periodo = constantes["PERIODO"]
    return (
        "BITALINO — ADQUISICIÓN Y PROCESAMIENTO\n"
        "======================================\n"
        f"Estado: {estado}\n"
        f"Canal configurado: {constantes['CANAL']}\n"
        f"PERIODO: {periodo} s\n"
        f"FS (1 / PERIODO): {1 / periodo:.2f} Hz\n"
        "Duración configurada: indefinida (hasta Apagar)\n"
        f"Tamaño máximo de lectura N: {constantes['N']}\n"
        f"Intervalo de tendencia: {parametros['TREND_INTERVAL_S']} s\n"
        f"Línea base: {parametros['BASELINE_DURATION_S']} s\n"
        f"Persistencia de alerta: {parametros['ALERT_PERSISTENCE_S']} s\n"
        f"Umbral RMS: +{parametros['RMS_INCREASE_THRESHOLD'] * 100:.0f}%\n"
        f"Umbral MDF: -{parametros['MDF_DECREASE_THRESHOLD'] * 100:.0f}%\n\n"
        f"Muestras recibidas: {info.n_medicion}\n"
        f"Último valor EMG (ADC): {info.ultimo_valor_emg}\n"
        f"Último RMS del bloque: {info.ultimo_rms:.3f}\n"
        f"Última MDF del bloque: {info.ultimo_mdf:.3f} Hz\n\n"
        f"Última trama recibida:\n  {texto_trama}\n\n"
        f"Últimas {len(info.muestras_recientes)} muestras:\n"
        f"{texto_muestras}\n\n"
        "Funciones del flujo:\n"
        "device.start() -> inicia BITalino\n"
        "device.read() -> recibe muestras\n"
        "procesar_bloque() -> calcula RMS/MDF\n"
        "cerrar_intervalo() -> resume y guarda CSV\n"
        "device.stop() -> detiene adquisición"
    )


def texto_alerta(minutos):
    return TEXTO_ALERTA.format(minutos=f"{minutos:g}")


def texto_calibracion(segundos):
    return f"Calibrando línea base ({segundos:g} s): mantén tu postura y ritmo de trabajo normales."


def texto_linea_base(rms, mdf):
    return f"Línea base: RMS = {rms:.3f} ADC · MDF = {mdf:.3f} Hz"
