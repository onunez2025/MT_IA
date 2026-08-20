# backend/tools/report_tools.py
"""
Herramienta de generación de reportes Excel de forecast.
Solo lectura de BD — el archivo generado no modifica ninguna tabla.
"""
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional

from connectors.sql_connector import azure_sql
from tools.utils import NETO_SQL
from config import settings

logger = logging.getLogger(__name__)

# Directorio destino para archivos generados.
# En producción Docker: /tmp (o el volumen montado si se configura FORECAST_OUTPUT_DIR).
# En local Windows: usar la variable de entorno FORECAST_OUTPUT_DIR.
_OUTPUT_DIR = os.getenv(
    "FORECAST_OUTPUT_DIR",
    "/tmp"   # fallback para Docker/EasyPanel
)


async def generate_forecast_report(year: int = 2026,
                                    month: int = 9,
                                    vendor_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Genera un archivo Excel con forecast de ventas para el mes indicado.
    Utiliza tendencia lineal sobre los últimos 3 meses reales disponibles.

    Fuentes:
      - SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD (ventas mensuales reales)
      - SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD (top vendedores YTD)
      - SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD (top categorías YTD)
      - SAP.SD_VENTAS (top clientes YTD)

    Returns: dict con file_path, forecast figures y resumen ejecutivo.
    """
    try:
        import openpyxl
        from openpyxl.styles import (PatternFill, Font, Alignment, Border, Side)
        from openpyxl.utils import get_column_letter
    except ImportError:
        return {"error": "openpyxl no está instalado. Ejecuta: pip install openpyxl"}

    # Excluir mes en curso si está incompleto (antes del día 25)
    now_dt = datetime.now()
    exclude_current = ""
    if now_dt.day < 25:
        exclude_current = (
            f"AND NOT (Anio = {now_dt.year} AND MesNumero = {now_dt.month})"
        )

    # ── 1. Historial mensual (años anterior y actual, excluyendo mes incompleto) ──
    hist = await azure_sql.query_readonly(f"""
        SELECT Anio, MesNumero, MesNombre,
               SUM(ImporteSoles)   AS ventas,
               SUM(UtilidadSoles)  AS utilidad
        FROM SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
        WHERE (Anio = {year} OR Anio = {year - 1})
          AND ImporteSoles > 0
          {exclude_current}
        GROUP BY Anio, MesNumero, MesNombre
        ORDER BY Anio, MesNumero
    """)

    # Últimos 3 meses completos del año actual (base para proyección)
    year_data = [r for r in hist if int(r["Anio"]) == year]
    year_data.sort(key=lambda r: int(r["MesNumero"]))
    last3 = year_data[-3:] if len(year_data) >= 3 else year_data

    # Tendencia lineal simple sobre meses completos
    if len(last3) >= 2:
        vals = [float(r["ventas"]) for r in last3]
        avg_growth = (vals[-1] - vals[0]) / max(len(vals) - 1, 1)
        base = vals[-1]
    else:
        avg_growth = 0
        base = float(last3[0]["ventas"]) if last3 else 20_000_000

    forecast_conservador = round(base * 0.97, 2)
    forecast_base        = round(base + avg_growth, 2)
    forecast_optimista   = round(base * 1.12, 2)

    # ── 2. Top vendedores YTD ──
    top_vend = await azure_sql.query_readonly(f"""
        SELECT TOP 15
            VendedorCodigo, VendedorNombre,
            SUM(ImporteSoles) AS ventas,
            SUM(UtilidadSoles) AS utilidad
        FROM SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
        WHERE Anio = {year} AND ImporteSoles > 0
        GROUP BY VendedorCodigo, VendedorNombre
        ORDER BY ventas DESC
    """)

    # ── 3. Top categorías YTD ──
    top_cat = await azure_sql.query_readonly(f"""
        SELECT TOP 15
            GrupoMaterialDirectorio AS categoria,
            SUM(ImporteSoles)       AS ventas,
            SUM(UtilidadSoles)      AS utilidad,
            AVG(MargenRealPorcentaje) AS margen_prom
        FROM SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
        WHERE Anio = {year} AND ImporteSoles > 0
          AND GrupoMaterialDirectorio IS NOT NULL
        GROUP BY GrupoMaterialDirectorio
        ORDER BY ventas DESC
    """)

    # ── 4. Top clientes YTD ──
    top_cli = await azure_sql.query_readonly(f"""
        SELECT TOP 15
            VC_solicitante_codigo AS codigo,
            MAX(VC_solicitante_razon_social) AS nombre,
            SUM({NETO_SQL}) AS ventas,
            COUNT(DISTINCT VC_documento_pago_numero) AS pedidos
        FROM SAP.SD_VENTAS
        WHERE IN_anio = {year}
          AND VC_solicitante_codigo IS NOT NULL
        GROUP BY VC_solicitante_codigo
        ORDER BY ventas DESC
    """)

    # ── 5. Construcción del Excel ──
    wb = openpyxl.Workbook()

    # Paleta corporativa MT
    _DARK_BLUE  = "001B48"
    _LIGHT_BLUE = "0077B6"
    _ACCENT     = "00B4D8"
    _WHITE      = "FFFFFF"
    _GRAY_BG    = "F5F7FA"
    _GREEN      = "28A745"
    _YELLOW     = "FFC107"

    month_names = {
        1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",
        7:"Julio",8:"Agosto",9:"Setiembre",10:"Octubre",11:"Noviembre",12:"Diciembre"
    }
    target_month_name = month_names.get(month, f"Mes {month}")

    def _hdr_fill(color=_DARK_BLUE):
        return PatternFill("solid", fgColor=color)

    def _hdr_font(bold=True, color=_WHITE):
        return Font(bold=bold, color=color, name="Calibri", size=11)

    def _num_fmt(ws, row, col, value, fmt="#,##0.00", bold=False):
        cell = ws.cell(row=row, column=col, value=value)
        cell.number_format = fmt
        cell.alignment = Alignment(horizontal="right")
        if bold:
            cell.font = Font(bold=True, name="Calibri", size=11)
        return cell

    def _thin_border():
        s = Side(style="thin", color="CCCCCC")
        return Border(left=s, right=s, top=s, bottom=s)

    def _set_col_widths(ws, widths):
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w

    # ── Hoja 1: Forecast ──
    ws1 = wb.active
    ws1.title = f"Forecast {target_month_name}"

    # Título principal
    ws1.merge_cells("A1:F1")
    c = ws1["A1"]
    c.value = f"FORECAST VENTAS — {target_month_name.upper()} {year}"
    c.fill  = _hdr_fill(_DARK_BLUE)
    c.font  = Font(bold=True, color=_WHITE, size=16, name="Calibri")
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws1.row_dimensions[1].height = 36

    ws1.merge_cells("A2:F2")
    ws1["A2"].value = f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}  |  MT Industrial S.A.C"
    ws1["A2"].font  = Font(italic=True, color="888888", size=10, name="Calibri")
    ws1["A2"].alignment = Alignment(horizontal="center")

    # Historial mensual
    row = 4
    ws1.merge_cells(f"A{row}:F{row}")
    ws1[f"A{row}"].value = "HISTORIAL MENSUAL"
    ws1[f"A{row}"].fill  = _hdr_fill(_LIGHT_BLUE)
    ws1[f"A{row}"].font  = _hdr_font()
    ws1[f"A{row}"].alignment = Alignment(horizontal="center")
    row += 1

    headers = ["Año", "Mes", "Nombre", "Ventas (S/)", "Utilidad (S/)", "Margen %"]
    for col, h in enumerate(headers, 1):
        c = ws1.cell(row=row, column=col, value=h)
        c.fill = _hdr_fill(_ACCENT)
        c.font = _hdr_font(color=_DARK_BLUE)
        c.border = _thin_border()
    row += 1

    for r in hist:
        v = float(r["ventas"] or 0)
        u = float(r["utilidad"] or 0)
        ws1.cell(row=row, column=1, value=int(r["Anio"]))
        ws1.cell(row=row, column=2, value=int(r["MesNumero"]))
        ws1.cell(row=row, column=3, value=str(r["MesNombre"]).capitalize())
        _num_fmt(ws1, row, 4, v)
        _num_fmt(ws1, row, 5, u)
        _num_fmt(ws1, row, 6, round(u/v*100, 1) if v else 0, "#,##0.0")
        if int(r["Anio"]) == year:
            ws1.row_dimensions[row].fill = PatternFill("solid", fgColor=_GRAY_BG)
        row += 1

    # Escenarios de forecast
    row += 1
    ws1.merge_cells(f"A{row}:F{row}")
    ws1[f"A{row}"].value = f"ESCENARIOS FORECAST — {target_month_name} {year}"
    ws1[f"A{row}"].fill  = _hdr_fill(_DARK_BLUE)
    ws1[f"A{row}"].font  = _hdr_font()
    ws1[f"A{row}"].alignment = Alignment(horizontal="center")
    row += 1

    scenarios = [
        ("Conservador (-3% base)",  forecast_conservador, _YELLOW,     _DARK_BLUE),
        ("Base (tendencia lineal)", forecast_base,        _LIGHT_BLUE, _WHITE),
        ("Optimista (+12% base)",   forecast_optimista,   _GREEN,      _WHITE),
    ]
    for label, value, fill_c, font_c in scenarios:
        ws1.cell(row=row, column=1, value=label).font = Font(bold=True, name="Calibri", size=12)
        c = ws1.cell(row=row, column=2, value=value)
        c.number_format = "#,##0.00"
        c.font  = Font(bold=True, color=font_c, name="Calibri", size=13)
        c.fill  = PatternFill("solid", fgColor=fill_c)
        c.alignment = Alignment(horizontal="center")
        ws1.row_dimensions[row].height = 22
        row += 1

    ws1.merge_cells(f"A{row}:F{row}")
    ws1[f"A{row}"].value = (
        "* Conservador: -3% sobre último mes real | "
        "Base: tendencia lineal 3 meses | "
        "Optimista: +12% sobre último mes real"
    )
    ws1[f"A{row}"].font = Font(italic=True, color="888888", size=9, name="Calibri")

    _set_col_widths(ws1, [8, 6, 16, 18, 18, 12])

    # ── Hoja 2: Top Vendedores YTD ──
    ws2 = wb.create_sheet("Top Vendedores YTD")
    ws2.merge_cells("A1:E1")
    c = ws2["A1"]
    c.value = f"TOP VENDEDORES YTD {year}"
    c.fill  = _hdr_fill(_DARK_BLUE)
    c.font  = Font(bold=True, color=_WHITE, size=14, name="Calibri")
    c.alignment = Alignment(horizontal="center")
    ws2.row_dimensions[1].height = 30

    hdrs2 = ["#", "Código", "Nombre Vendedor", "Ventas YTD (S/)", "Utilidad YTD (S/)"]
    for col, h in enumerate(hdrs2, 1):
        c = ws2.cell(row=2, column=col, value=h)
        c.fill = _hdr_fill(_LIGHT_BLUE)
        c.font = _hdr_font()
        c.border = _thin_border()

    total_v2 = sum(float(r["ventas"] or 0) for r in top_vend)
    for i, r in enumerate(top_vend, 1):
        v = float(r["ventas"] or 0)
        u = float(r["utilidad"] or 0)
        ws2.cell(row=i+2, column=1, value=i)
        ws2.cell(row=i+2, column=2, value=str(r.get("VendedorCodigo") or ""))
        ws2.cell(row=i+2, column=3, value=str(r.get("VendedorNombre") or ""))
        _num_fmt(ws2, i+2, 4, v, bold=(i == 1))
        _num_fmt(ws2, i+2, 5, u)

    _set_col_widths(ws2, [5, 12, 36, 20, 20])

    # ── Hoja 3: Top Categorías ──
    ws3 = wb.create_sheet("Top Categorías")
    ws3.merge_cells("A1:E1")
    c = ws3["A1"]
    c.value = f"TOP CATEGORÍAS YTD {year}"
    c.fill  = _hdr_fill(_DARK_BLUE)
    c.font  = Font(bold=True, color=_WHITE, size=14, name="Calibri")
    c.alignment = Alignment(horizontal="center")
    ws3.row_dimensions[1].height = 30

    hdrs3 = ["#", "Categoría", "Ventas YTD (S/)", "Utilidad YTD (S/)", "Margen Prom %"]
    for col, h in enumerate(hdrs3, 1):
        c = ws3.cell(row=2, column=col, value=h)
        c.fill = _hdr_fill(_LIGHT_BLUE)
        c.font = _hdr_font()
        c.border = _thin_border()

    for i, r in enumerate(top_cat, 1):
        v = float(r["ventas"] or 0)
        u = float(r["utilidad"] or 0)
        m = float(r["margen_prom"] or 0)
        ws3.cell(row=i+2, column=1, value=i)
        ws3.cell(row=i+2, column=2, value=str(r.get("categoria") or ""))
        _num_fmt(ws3, i+2, 3, v, bold=(i == 1))
        _num_fmt(ws3, i+2, 4, u)
        _num_fmt(ws3, i+2, 5, round(m, 1), "#,##0.0")

    _set_col_widths(ws3, [5, 40, 20, 20, 16])

    # ── Hoja 4: Top Clientes ──
    ws4 = wb.create_sheet("Top Clientes")
    ws4.merge_cells("A1:E1")
    c = ws4["A1"]
    c.value = f"TOP CLIENTES YTD {year}"
    c.fill  = _hdr_fill(_DARK_BLUE)
    c.font  = Font(bold=True, color=_WHITE, size=14, name="Calibri")
    c.alignment = Alignment(horizontal="center")
    ws4.row_dimensions[1].height = 30

    hdrs4 = ["#", "Código", "Nombre Cliente", "Ventas YTD (S/)", "Pedidos"]
    for col, h in enumerate(hdrs4, 1):
        c = ws4.cell(row=2, column=col, value=h)
        c.fill = _hdr_fill(_LIGHT_BLUE)
        c.font = _hdr_font()
        c.border = _thin_border()

    for i, r in enumerate(top_cli, 1):
        v = float(r["ventas"] or 0)
        ws4.cell(row=i+2, column=1, value=i)
        ws4.cell(row=i+2, column=2, value=str(r.get("codigo") or ""))
        ws4.cell(row=i+2, column=3, value=str(r.get("nombre") or ""))
        _num_fmt(ws4, i+2, 4, v, bold=(i == 1))
        ws4.cell(row=i+2, column=5, value=int(r.get("pedidos") or 0))

    _set_col_widths(ws4, [5, 14, 40, 20, 10])

    # ── 6. Guardar ──
    filename = f"Forecast_{target_month_name}_{year}.xlsx"
    filepath = os.path.join(_OUTPUT_DIR, filename)
    file_saved = False
    try:
        os.makedirs(_OUTPUT_DIR, exist_ok=True)
        wb.save(filepath)
        file_saved = True
        logger.info(f"Forecast report saved: {filepath}")
    except PermissionError:
        # Archivo en uso — agregar timestamp al nombre
        try:
            ts = datetime.now().strftime("%H%M%S")
            filename = f"Forecast_{target_month_name}_{year}_{ts}.xlsx"
            filepath = os.path.join(_OUTPUT_DIR, filename)
            wb.save(filepath)
            file_saved = True
            logger.info(f"Forecast report saved (retry): {filepath}")
        except Exception as e:
            logger.warning(f"Could not save forecast file: {e}")
            filepath = None
    except Exception as e:
        logger.warning(f"Could not save forecast file: {e}")
        filepath = None

    # Construir link de descarga si hay URL pública configurada
    download_url = None
    if file_saved and settings.public_url:
        base = settings.public_url.rstrip("/")
        download_url = f"{base}/reports/{filename}"

    return {
        "file_path": filepath if file_saved else None,
        "filename": filename if file_saved else None,
        "file_saved": file_saved,
        "download_url": download_url,
        "period": f"{year}-{month:02d}",
        "target_month": target_month_name,
        "forecast_conservador": forecast_conservador,
        "forecast_base": forecast_base,
        "forecast_optimista": forecast_optimista,
        "base_months_used": [
            f"{int(r['Anio'])}-{int(r['MesNumero']):02d}" for r in last3
        ],
        "sheets": ["Forecast", "Top Vendedores YTD", "Top Categorías", "Top Clientes"],
        "timestamp": datetime.utcnow().isoformat(),
    }
