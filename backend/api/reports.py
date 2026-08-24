# backend/api/reports.py
"""
Endpoints para reportes y análisis
Incluye filtros avanzados, análisis temporal, comparativas y rankings
"""
from fastapi import APIRouter, Query, Body, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from enum import Enum
from layers.analyzer import DataAnalyzer, PeriodType
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])
analyzer = DataAnalyzer()


# ======================== MODELOS PYDANTIC ========================

class FilterRequest(BaseModel):
    """Filtros avanzados para reportes"""
    date_range: Optional[Dict[str, str]] = Field(None, description="Rango de fechas {start_date, end_date}")
    price_range: Optional[Dict[str, float]] = Field(None, description="Rango de precios {min, max}")
    min_margin: Optional[float] = Field(None, description="Margen mínimo (%)")
    customers: Optional[List[int]] = Field(None, description="IDs de clientes a filtrar")
    sellers: Optional[List[int]] = Field(None, description="IDs de vendedores a filtrar")
    min_units: Optional[int] = Field(None, description="Unidades mínimas vendidas")


class PeriodAnalysisRequest(BaseModel):
    """Solicitud de análisis por período"""
    period_type: PeriodType = Field(PeriodType.MONTHLY, description="Tipo de período")
    start_date: str = Field(..., description="Fecha inicio (YYYY-MM-DD)")
    end_date: str = Field(..., description="Fecha fin (YYYY-MM-DD)")
    filters: Optional[FilterRequest] = Field(None, description="Filtros adicionales")
    top_x: int = Field(10, description="Cantidad de top productos (configurable)")


class ComparePeriodsRequest(BaseModel):
    """Solicitud de comparación entre períodos"""
    period_type: PeriodType = Field(PeriodType.MONTHLY, description="Tipo de período")
    period1_start: str = Field(..., description="Periodo 1 - Fecha inicio")
    period1_end: str = Field(..., description="Periodo 1 - Fecha fin")
    period2_start: str = Field(..., description="Periodo 2 - Fecha inicio")
    period2_end: str = Field(..., description="Periodo 2 - Fecha fin")
    filters: Optional[FilterRequest] = Field(None, description="Filtros adicionales")


# ======================== ENDPOINTS ========================

@router.post("/filter", summary="Aplicar filtros avanzados")
async def apply_filters(filters: FilterRequest) -> Dict[str, Any]:
    """
    Aplica filtros avanzados a los datos

    **Filtros soportados:**
    - Rango de fechas (flexible)
    - Rango de precios
    - Margen mínimo
    - Clientes específicos (multi-select)
    - Vendedores específicos (multi-select)
    - Unidades mínimas

    **Returns:** Datos filtrados
    """
    try:
        logger.info(f"Aplicando filtros: {filters.dict()}")

        # TODO: Implementar lógica de filtros
        result = {
            "status": "success",
            "filters_applied": filters.dict(),
            "total_records": 0,
            "data": []
        }

        return result

    except Exception as e:
        logger.error(f"Error aplicando filtros: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/daily", summary="Análisis diario")
async def daily_analysis(request: PeriodAnalysisRequest) -> Dict[str, Any]:
    """
    Análisis de ventas diarias
    - Top X productos del día
    - Comparativa vs promedio semanal
    - Clientes activos
    - Gráfico hora por hora
    """
    try:
        start_date = datetime.fromisoformat(request.start_date)
        end_date = datetime.fromisoformat(request.end_date)

        analysis = await analyzer.get_period_analysis(
            period_type=PeriodType.DAILY,
            start_date=start_date,
            end_date=end_date,
            filters=request.filters.dict() if request.filters else None,
            top_x=request.top_x
        )

        return analysis

    except Exception as e:
        logger.error(f"Error en análisis diario: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/weekly", summary="Análisis semanal")
async def weekly_analysis(request: PeriodAnalysisRequest) -> Dict[str, Any]:
    """
    Análisis de ventas semanales
    - Ranking de productos (Top X)
    - Comparativa semana actual vs anterior
    - Productos mejor/peor desempeño
    - Tendencia de crecimiento
    """
    try:
        start_date = datetime.fromisoformat(request.start_date)
        end_date = datetime.fromisoformat(request.end_date)

        analysis = await analyzer.get_period_analysis(
            period_type=PeriodType.WEEKLY,
            start_date=start_date,
            end_date=end_date,
            filters=request.filters.dict() if request.filters else None,
            top_x=request.top_x
        )

        return analysis

    except Exception as e:
        logger.error(f"Error en análisis semanal: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/monthly", summary="Análisis mensual")
async def monthly_analysis(request: PeriodAnalysisRequest) -> Dict[str, Any]:
    """
    Análisis de ventas mensuales
    - Evolución diaria dentro del mes
    - Comparativa mes actual vs anterior
    - Producto estrella (Top X)
    - Margen de ganancias por semana
    - Proyección de cierre
    """
    try:
        start_date = datetime.fromisoformat(request.start_date)
        end_date = datetime.fromisoformat(request.end_date)

        analysis = await analyzer.get_period_analysis(
            period_type=PeriodType.MONTHLY,
            start_date=start_date,
            end_date=end_date,
            filters=request.filters.dict() if request.filters else None,
            top_x=request.top_x
        )

        return analysis

    except Exception as e:
        logger.error(f"Error en análisis mensual: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/quarterly", summary="Análisis trimestral")
async def quarterly_analysis(request: PeriodAnalysisRequest) -> Dict[str, Any]:
    """
    Análisis de ventas trimestrales
    - Análisis de estacionalidad
    - Productos más consistentes (Top X)
    - Crecimiento trimestral
    - Comparativa trimestre vs trimestre
    """
    try:
        start_date = datetime.fromisoformat(request.start_date)
        end_date = datetime.fromisoformat(request.end_date)

        analysis = await analyzer.get_period_analysis(
            period_type=PeriodType.QUARTERLY,
            start_date=start_date,
            end_date=end_date,
            filters=request.filters.dict() if request.filters else None,
            top_x=request.top_x
        )

        return analysis

    except Exception as e:
        logger.error(f"Error en análisis trimestral: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/compare", summary="Comparar dos períodos")
async def compare_periods(request: ComparePeriodsRequest) -> Dict[str, Any]:
    """
    Compara dos períodos lado a lado

    Muestra:
    - Datos de ambos períodos
    - Variaciones (%, valor absoluto)
    - Cambios en ventas, margen, unidades
    - Ranking de cambios (qué subió/bajó)
    """
    try:
        date1_start = datetime.fromisoformat(request.period1_start)
        date1_end = datetime.fromisoformat(request.period1_end)
        date2_start = datetime.fromisoformat(request.period2_start)
        date2_end = datetime.fromisoformat(request.period2_end)

        comparison = await analyzer.compare_periods(
            period_type=request.period_type,
            date1_start=date1_start,
            date1_end=date1_end,
            date2_start=date2_start,
            date2_end=date2_end,
            filters=request.filters.dict() if request.filters else None
        )

        return comparison

    except Exception as e:
        logger.error(f"Error en comparación de períodos: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/rankings", summary="Rankings configurables (Top X)")
async def get_rankings(
    type: str = Query(..., description="products|sellers|customers|categories"),
    limit: int = Query(10, ge=1, le=100, description="Top X (configurable de 1 a 100)"),
    period: str = Query("monthly", description="daily|weekly|monthly|quarterly|yearly"),
    start_date: Optional[str] = Query(None, description="Fecha inicio (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Fecha fin (YYYY-MM-DD)")
) -> List[Dict[str, Any]]:
    """
    Rankings configurables con Top X personalizable

    **Parámetros:**
    - `type`: Tipo de ranking (products, sellers, customers, categories)
    - `limit`: Cantidad de items (configurable: 1-100) ← AQUÍ VA TU NÚMERO X
    - `period`: Período a analizar
    - `start_date` / `end_date`: Rango de fechas (opcional)

    **Ejemplo:** /api/reports/rankings?type=products&limit=15&period=monthly
    → Retorna Top 15 productos del mes
    """
    try:
        start = datetime.fromisoformat(start_date) if start_date else datetime.now() - timedelta(days=30)
        end = datetime.fromisoformat(end_date) if end_date else datetime.now()
        period_type = PeriodType(period)

        rankings = await analyzer.get_rankings(
            ranking_type=type,
            limit=limit,
            period_type=period_type,
            start_date=start,
            end_date=end
        )

        return rankings

    except Exception as e:
        logger.error(f"Error obteniendo rankings: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


# Documentación de ejemplo
"""
EJEMPLOS DE USO:

1. TOP 10 PRODUCTOS DEL MES:
   GET /api/reports/rankings?type=products&limit=10&period=monthly

2. TOP 5 CLIENTES POR MARGEN (DIARIO):
   GET /api/reports/rankings?type=customers&limit=5&period=daily

3. TOP 20 CATEGORÍAS DEL TRIMESTRE:
   GET /api/reports/rankings?type=categories&limit=20&period=quarterly

4. ANÁLISIS MENSUAL CON FILTROS:
   POST /api/reports/monthly
   {
     "period_type": "monthly",
     "start_date": "2026-08-01",
     "end_date": "2026-08-31",
     "top_x": 15,
     "filters": {
       "min_margin": 50,
       "price_range": {"min": 100, "max": 5000}
     }
   }

5. COMPARAR DOS MESES:
   POST /api/reports/compare
   {
     "period_type": "monthly",
     "period1_start": "2026-07-01",
     "period1_end": "2026-07-31",
     "period2_start": "2026-08-01",
     "period2_end": "2026-08-31"
   }
"""
