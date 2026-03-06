from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import csv
import os

app = Flask(__name__, static_folder=".")
CORS(app)

CSV_PATH = "datos_rendimiento_universidad.csv"


# ── helpers (inline, sin imports de tus módulos) ──────────────────────────────

def _leer_csv(filtro_carrera=None, filtro_anio=None):
    filas = []
    with open(CSV_PATH, mode="r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                row["calificacion"] = float(row["calificacion"])
                row["semestre"] = int(row["semestre"])
                row["año"] = int(row["año"])
            except ValueError:
                continue
            if filtro_carrera and filtro_carrera != "todas" and row["carrera"] != filtro_carrera:
                continue
            if filtro_anio and row["año"] != int(filtro_anio):
                continue
            filas.append(row)
    return filas


def _indice_reprobacion(filas, min_ap=6.0):
    totales, reprobadas = {}, {}
    for r in filas:
        m = r["materia"]
        totales[m] = totales.get(m, 0) + 1
        if r["calificacion"] < min_ap:
            reprobadas[m] = reprobadas.get(m, 0) + 1
    return {m: ((reprobadas.get(m, 0) / totales[m]) * 100, reprobadas.get(m, 0), totales[m])
            for m in totales}


def _promedio_carrera(filas):
    datos = {}
    for r in filas:
        c = r["carrera"]
        if c not in datos:
            datos[c] = [0.0, 0]
        datos[c][0] += r["calificacion"]
        datos[c][1] += 1
    return {c: v[0] / v[1] for c, v in datos.items() if v[1]}


def _tendencia_semestre(filas):
    datos = {}
    for r in filas:
        key = (r["año"], r["semestre"])
        if key not in datos:
            datos[key] = [0.0, 0]
        datos[key][0] += r["calificacion"]
        datos[key][1] += 1
    return {f"S{s} {a}": v[0] / v[1] for (a, s), v in sorted(datos.items()) if v[1]}


def _alumnos_riesgo(filas, umbral=6.0):
    return [r for r in filas if r["calificacion"] < umbral]


def _promedio_global(filas):
    if not filas:
        return 0.0
    return sum(r["calificacion"] for r in filas) / len(filas)


def _tasa_reprobacion_global(filas, umbral=6.0):
    if not filas:
        return 0.0
    reprobados = sum(1 for r in filas if r["calificacion"] < umbral)
    return round((reprobados / len(filas)) * 100, 1)


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.route("/api/filtros")
def filtros():
    """Devuelve años y carreras únicos encontrados en el CSV."""
    años = set()
    carreras = set()
    with open(CSV_PATH, mode="r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                años.add(int(row["año"]))
            except ValueError:
                pass
            if row.get("carrera"):
                carreras.add(row["carrera"])
    return jsonify({
        "años": sorted(años, reverse=True),
        "carreras": sorted(carreras)
    })


@app.route("/api/summary")
def summary():
    from flask import request
    carrera = request.args.get("carrera")
    anio = request.args.get("anio")
    filas = _leer_csv(carrera, anio)

    prom_global = round(_promedio_global(filas), 2)
    tasa_repr = _tasa_reprobacion_global(filas)
    en_riesgo = _alumnos_riesgo(filas)

    idx = _indice_reprobacion(filas)
    materia_max = max(idx.items(), key=lambda x: x[1][0]) if idx else None

    return jsonify({
        "average_grade": prom_global,
        "fail_rate": tasa_repr,
        "at_risk_count": len(en_riesgo),
        "highest_fail_subject": materia_max[0] if materia_max else "-",
        "highest_fail_pct": round(materia_max[1][0], 1) if materia_max else 0,
    })


@app.route("/api/reprobacion")
def reprobacion():
    from flask import request
    carrera = request.args.get("carrera")
    anio = request.args.get("anio")
    filas = _leer_csv(carrera, anio)
    idx = _indice_reprobacion(filas)
    ordenado = sorted(idx.items(), key=lambda x: x[1][0], reverse=True)[:6]
    return jsonify([
        {"materia": m, "indice": round(v[0], 1), "reprobadas": v[1], "total": v[2]}
        for m, v in ordenado
    ])


@app.route("/api/promedios_carrera")
def promedios_carrera():
    from flask import request
    anio = request.args.get("anio")
    filas = _leer_csv(filtro_anio=anio)
    proms = _promedio_carrera(filas)
    ranking = sorted(proms.items(), key=lambda x: x[1], reverse=True)
    return jsonify([{"carrera": c, "promedio": round(p, 2)} for c, p in ranking])


@app.route("/api/tendencia")
def tendencia():
    from flask import request
    carrera = request.args.get("carrera")
    anio = request.args.get("anio")
    filas = _leer_csv(carrera, anio)
    tend = _tendencia_semestre(filas)
    return jsonify([{"semestre": k, "promedio": round(v, 2)} for k, v in tend.items()])


@app.route("/api/riesgo")
def riesgo():
    from flask import request
    carrera = request.args.get("carrera")
    anio = request.args.get("anio")
    filas = _leer_csv(carrera, anio)
    en_riesgo = sorted(_alumnos_riesgo(filas), key=lambda r: r["calificacion"])
    return jsonify([
        {
            "id": r["id_estudiante"],
            "carrera": r["carrera"],
            "materia": r["materia"],
            "calificacion": r["calificacion"],
        }
        for r in en_riesgo
    ])


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
