import time
import numpy as np


def vecincos_vivos(celula, i, j, filas, columnas):
    """Calcula la cantidad de células vivas alrededor de la posición (i, j)."""
    vivos = 0

    # Ortogonales (Arriba, Abajo, Izquierda, Derecha)
    if (i - 1) >= 0 and (celula[i - 1][j] == 1):
        vivos += 1
    if (i + 1) <= (filas - 1) and (celula[i + 1][j] == 1):
        vivos += 1
    if (j - 1) >= 0 and (celula[i][j - 1] == 1):
        vivos += 1
    if (j + 1) <= (columnas - 1) and (celula[i][j + 1] == 1):
        vivos += 1

    # Diagonales
    if i - 1 >= 0 and j - 1 >= 0 and (celula[i - 1][j - 1] == 1):
        vivos += 1
    if i + 1 <= (filas - 1) and j + 1 <= (columnas - 1) and (celula[i + 1][j + 1] == 1):
        vivos += 1
    if i - 1 >= 0 and j + 1 <= (columnas - 1) and (celula[i - 1][j + 1] == 1):
        vivos += 1
    if i + 1 <= (filas - 1) and j - 1 >= 0 and (celula[i + 1][j - 1] == 1):
        vivos += 1

    return vivos


def regla_actualizacion(matriz, filas, columnas):
    """Aplica la lógica de actualización sobre la implementación."""
    nueva = matriz.copy()
    for i in range(filas):
        for j in range(columnas):
            v_vivos = vecincos_vivos(matriz, i, j, filas, columnas)

            if matriz[i, j] == 1 and v_vivos < 2:
                nueva[i, j] = 0
            elif matriz[i, j] == 1 and (v_vivos == 2 or v_vivos == 3):
                nueva[i, j] = 1
            elif matriz[i, j] == 1 and v_vivos > 3:
                nueva[i, j] = 0
            elif matriz[i, j] == 0 and v_vivos == 3:
                nueva[i, j] = 1

    return nueva


# MÓDULO DE BENCHMARKING


def ejecutar_benchmark(tamanios: list[tuple[int, int]], generaciones: int = 5) -> None:

    print("      BENCHMARK      ")

    print(
        f"{'Tamaño':<15} | {'Generaciones':<14} | {'Tiempo Total (s)':<18} | {'Promedio/Gen (s)':<18}"
    )

    for filas, columnas in tamanios:
        # Generar matriz inicial
        matriz = np.random.choice([0, 1], size=(filas, columnas))

        # Medición del tiempo de cómputo puro
        inicio = time.time()

        for _ in range(generaciones):
            matriz = regla_actualizacion(matriz, filas, columnas)

        fin = time.time()

        tiempo_total_s = fin - inicio
        tiempo_promedio_gen_s = tiempo_total_s / generaciones

        dimension_str = f"{filas}x{columnas}"
        print(
            f"{dimension_str:<15} | {generaciones:<14} | {tiempo_total_s} | {tiempo_promedio_gen_s}"
        )


if __name__ == "__main__":
    # Configuración de pruebas
    TAMANIOS = [(100, 100), (500, 500), (1000, 1000)]
    GENERACIONES = 5

    ejecutar_benchmark(TAMANIOS, generaciones=GENERACIONES)
