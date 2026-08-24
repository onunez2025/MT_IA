# backend/layers/analyzer.py
"""
Análisis de datos de ventas por períodos y filtros
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class PeriodType(str, Enum):
    """Tipos de períodos soportados"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class DataAnalyzer:
    """
    Analizador de datos de ventas
    Proporciona análisis temporal, comparativas y rankings configurables
    """

    def __init__(self, data_source=None):
        """
        Args:
            data_source: Conector a base de datos (DB connector)
        """
        self.data_source = data_source

    async def get_period_analysis(
        self,
        period_type: PeriodType,
        start_date: datetime,
        end_date: datetime,
        filters: Optional[Dict[str, Any]] = None,
        top_x: int = 10
    ) -> Dict[str, Any]:
        """
        Análisis de datos por período (diario, semanal, mensual, etc.)

        Args:
            period_type: Tipo de período (DAILY, WEEKLY, MONTHLY, etc.)
            start_date: Fecha inicio
            end_date: Fecha fin
            filters: Filtros adicionales (clientes, categorías, etc.)
            top_x: Cantidad de top productos a retornar (configurable)

        Returns:
            Dict con análisis del período
        """
        try:
            logger.info(f"Analizando período {period_type} de {start_date} a {end_date}")

            # TODO: Implementar consulta a BD
            # data = await self.data_source.query_by_period(period_type, start_date, end_date, filters)

            # Estructura esperada
            analysis = {
                "period_type": period_type,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "total_sales": 0,
                "total_units": 0,
                "top_products": [],  # Top X productos
                "total_margin": 0,
                "average_order_value": 0,
                "active_customers": 0
            }

            return analysis

        except Exception as e:
            logger.error(f"Error en análisis de período: {str(e)}")
            raise

    async def compare_periods(
        self,
        period_type: PeriodType,
        date1_start: datetime,
        date1_end: datetime,
        date2_start: datetime,
        date2_end: datetime,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Compara dos períodos lado a lado

        Args:
            period_type: Tipo de período
            date1_start, date1_end: Rango del período 1
            date2_start, date2_end: Rango del período 2
            filters: Filtros adicionales

        Returns:
            Comparativa entre períodos
        """
        try:
            period1 = await self.get_period_analysis(
                period_type, date1_start, date1_end, filters
            )
            period2 = await self.get_period_analysis(
                period_type, date2_start, date2_end, filters
            )

            # Calcular variaciones
            sales_change = self._calculate_change(
                period1.get("total_sales", 0),
                period2.get("total_sales", 0)
            )

            comparison = {
                "period1": {
                    "date_range": f"{date1_start.date()} to {date1_end.date()}",
                    "data": period1
                },
                "period2": {
                    "date_range": f"{date2_start.date()} to {date2_end.date()}",
                    "data": period2
                },
                "changes": {
                    "sales_change_percent": sales_change,
                    "sales_change_value": period2.get("total_sales", 0) - period1.get("total_sales", 0),
                    "units_change_percent": self._calculate_change(
                        period1.get("total_units", 0),
                        period2.get("total_units", 0)
                    ),
                    "margin_change_percent": self._calculate_change(
                        period1.get("total_margin", 0),
                        period2.get("total_margin", 0)
                    )
                }
            }

            return comparison

        except Exception as e:
            logger.error(f"Error en comparativa de períodos: {str(e)}")
            raise

    async def get_rankings(
        self,
        ranking_type: str,  # "products", "sellers", "customers", "categories"
        limit: int = 10,  # Top X (configurable)
        period_type: PeriodType = PeriodType.MONTHLY,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Rankings configurables (Top X)

        Args:
            ranking_type: Tipo de ranking (products, sellers, customers, categories)
            limit: Cantidad de items (configurable, ej: Top 5, Top 20)
            period_type: Período a analizar
            start_date: Fecha inicio (si no se proporciona, usa período actual)
            end_date: Fecha fin
            filters: Filtros adicionales

        Returns:
            Lista de top X items
        """
        try:
            logger.info(f"Obteniendo Top {limit} {ranking_type}")

            # TODO: Implementar consulta a BD con LIMIT
            rankings = [
                {
                    "rank": i + 1,
                    "name": f"Item {i + 1}",
                    "value": 1000 * (limit - i),  # Placeholder
                    "percent_of_total": 100 / limit
                }
                for i in range(limit)
            ]

            return rankings

        except Exception as e:
            logger.error(f"Error obteniendo rankings: {str(e)}")
            raise

    @staticmethod
    def _calculate_change(value1: float, value2: float) -> float:
        """Calcula porcentaje de cambio entre dos valores"""
        if value1 == 0:
            return 0 if value2 == 0 else 100
        return round(((value2 - value1) / value1) * 100, 2)


# Instancia singleton
analyzer = DataAnalyzer()
