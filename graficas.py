
from __future__ import annotations

import argparse
import os
from collections import defaultdict

from matplotlib.axes import Axes
from matplotlib.figure import Figure

COLOR_SECUENCIAL = "#444444"


def _paralelos(resultados):
    return [r for r in resultados if r["hilos"] and r["motor"] != "Secuencial"]


def _tamanios(resultados):
    return sorted({r["filas"] for r in resultados})


def grafica_tiempo(ax: Axes, resultados: list[dict], log: bool = True) -> None:
    """Tiempo de ejecución vs. tamaño de matriz (una línea por motor/hilos)."""
    series = defaultdict(dict)
    for r in resultados:
        etiqueta = r["motor"] if r["motor"] == "Secuencial" else f"{r['motor']} - {r['hilos']} hilos"
        series[etiqueta][r["filas"]] = r["tiempo_gen_ms"]

    def orden(et):
        return (0, 0, et) if et == "Secuencial" else (1, int(et.rsplit(" - ", 1)[1].split()[0]), et)

    for et in sorted(series, key=orden):
        xs = sorted(series[et])
        estilo = dict(color=COLOR_SECUENCIAL, linewidth=2.5) if et == "Secuencial" else dict(linewidth=1.8)
        ax.plot(xs, [series[et][x] for x in xs], marker="o", label=et, **estilo)

    ax.set_title("Tiempo por generación vs. tamaño de matriz")
    ax.set_xlabel("Tamaño (n en matriz n x n)")
    ax.set_ylabel("Tiempo por generación (ms)")
    ax.set_xticks(_tamanios(resultados))
    if log:
        ax.set_yscale("log")
    ax.grid(True, alpha=0.3, which="both")
    if series:
        ax.legend(fontsize=8)


def _por_hilos(ax: Axes, resultados: list[dict], campo: str, titulo: str, ylabel: str, ideal) -> None:
    series = defaultdict(dict)
    motores = {r["motor"] for r in _paralelos(resultados)}
    for r in _paralelos(resultados):
        et = f"{r['tamanio']}" if len(motores) == 1 else f"{r['motor']} - {r['tamanio']}"
        series[et][r["hilos"]] = r[campo]

    todos_hilos = sorted({h for s in series.values() for h in s})
    if todos_hilos:
        rango = [1] + todos_hilos if todos_hilos[0] != 1 else todos_hilos
        ax.plot(rango, [ideal(h) for h in rango], "--", color="#999999", label="Ideal")

    def orden(et):
        return int(et.rsplit(" - ", 1)[-1].split("x")[0])

    for et in sorted(series, key=orden):
        xs = sorted(series[et])
        ax.plot(xs, [series[et][x] for x in xs], marker="o", linewidth=1.8, label=et)

    ax.set_title(titulo)
    ax.set_xlabel("Número de hilos / procesos")
    ax.set_ylabel(ylabel)
    if todos_hilos:
        ax.set_xticks(rango)
    ax.grid(True, alpha=0.3)
    if series:
        ax.legend(fontsize=8)
    else:
        ax.text(0.5, 0.5, "Sin datos de motores paralelos todavía",
                ha="center", va="center", transform=ax.transAxes, color="#888888")


def grafica_speedup(ax: Axes, resultados: list[dict]) -> None:
    _por_hilos(ax, resultados, "speedup", "Speedup vs. número de hilos/procesos",
               "Speedup (T_sec / T_par)", ideal=lambda h: h)


def grafica_eficiencia(ax: Axes, resultados: list[dict]) -> None:
    _por_hilos(ax, resultados, "eficiencia", "Eficiencia vs. número de hilos/procesos",
               "Eficiencia (Speedup / hilos)", ideal=lambda h: 1.0)


GRAFICAS = {
    "tiempo_vs_tamanio": grafica_tiempo,
    "speedup_vs_hilos": grafica_speedup,
    "eficiencia_vs_hilos": grafica_eficiencia,
}


def exportar_png(resultados: list[dict], carpeta: str, dpi: int = 150) -> list[str]:
    os.makedirs(carpeta, exist_ok=True)
    rutas = []
    for nombre, fn in GRAFICAS.items():
        fig = Figure(figsize=(7, 4.5), dpi=dpi)
        fn(fig.add_subplot(111), resultados)
        fig.tight_layout()
        ruta = os.path.join(carpeta, f"{nombre}.png")
        fig.savefig(ruta)
        rutas.append(ruta)
    return rutas


if __name__ == "__main__":
    from benchmark import cargar_csv

    p = argparse.ArgumentParser(description="Genera las gráficas de rendimiento")
    p.add_argument("csv", nargs="?", default="resultados.csv")
    p.add_argument("--carpeta", default="graficas")
    a = p.parse_args()
    for ruta in exportar_png(cargar_csv(a.csv), a.carpeta):
        print("Guardada:", ruta)
