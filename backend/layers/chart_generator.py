# backend/layers/chart_generator.py
"""
Generador de gráficos y visualizaciones para reportes
Soporta: línea, barras, heatmap, waterfall, tabla dinámica
"""
from typing import Dict, List, Any, Optional
from enum import Enum
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ChartType(str, Enum):
    """Tipos de gráficos soportados"""
    LINE = "line"           # Evolución temporal
    BAR = "bar"             # Comparativas
    HEATMAP = "heatmap"     # Cuándo se vende más
    WATERFALL = "waterfall" # Desglose de cambios
    TABLE = "table"         # Tabla dinámica


class ChartGenerator:
    """
    Generador de datos para gráficos en formato compatible con Chart.js/Recharts
    """

    def __init__(self):
        pass

    async def generate_line_chart(
        self,
        data: List[Dict[str, Any]],
        x_axis: str,
        y_axis: str,
        title: str,
        legend_label: str = "Valor"
    ) -> Dict[str, Any]:
        """
        Genera gráfico de línea (evolución temporal)

        Args:
            data: Lista de datos con x_axis y y_axis
            x_axis: Campo para eje X (ej: "date", "day")
            y_axis: Campo para eje Y (ej: "sales", "units")
            title: Título del gráfico
            legend_label: Etiqueta de la serie

        Returns:
            Formato compatible con Chart.js/Recharts
        """
        try:
            logger.info(f"Generando gráfico de línea: {title}")

            # Extraer valores
            labels = [str(item.get(x_axis)) for item in data]
            values = [item.get(y_axis, 0) for item in data]

            chart = {
                "type": "line",
                "title": title,
                "data": {
                    "labels": labels,
                    "datasets": [
                        {
                            "label": legend_label,
                            "data": values,
                            "borderColor": "rgb(75, 192, 192)",
                            "backgroundColor": "rgba(75, 192, 192, 0.1)",
                            "tension": 0.4,
                            "fill": True
                        }
                    ]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": title
                        }
                    },
                    "scales": {
                        "y": {"beginAtZero": True}
                    }
                }
            }

            return chart

        except Exception as e:
            logger.error(f"Error generando línea chart: {str(e)}")
            raise

    async def generate_bar_chart(
        self,
        data: List[Dict[str, Any]],
        categories: str,
        value: str,
        title: str
    ) -> Dict[str, Any]:
        """
        Genera gráfico de barras (comparativas Top X)

        Args:
            data: Lista de datos
            categories: Campo con categorías (ej: "product_name")
            value: Campo con valores (ej: "sales")
            title: Título del gráfico

        Returns:
            Formato compatible con Chart.js/Recharts
        """
        try:
            logger.info(f"Generando gráfico de barras: {title}")

            labels = [str(item.get(categories)) for item in data]
            values = [item.get(value, 0) for item in data]

            # Generar colores degradados
            colors = [f"rgba({50 + i*10}, {150}, {200}, 0.8)" for i in range(len(data))]

            chart = {
                "type": "bar",
                "title": title,
                "data": {
                    "labels": labels,
                    "datasets": [
                        {
                            "label": value,
                            "data": values,
                            "backgroundColor": colors,
                            "borderColor": colors,
                            "borderWidth": 1
                        }
                    ]
                },
                "options": {
                    "responsive": True,
                    "indexAxis": "y" if len(labels) > 10 else "x",  # Horizontal si hay muchos
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": title
                        }
                    },
                    "scales": {
                        "y": {"beginAtZero": True}
                    }
                }
            }

            return chart

        except Exception as e:
            logger.error(f"Error generando bar chart: {str(e)}")
            raise

    async def generate_heatmap(
        self,
        data: List[Dict[str, Any]],
        x_field: str,
        y_field: str,
        value_field: str,
        title: str
    ) -> Dict[str, Any]:
        """
        Genera heatmap (cuándo se vende más)

        Args:
            data: Datos con x, y, value
            x_field: Eje X (ej: "day_of_week")
            y_field: Eje Y (ej: "hour")
            value_field: Valor de intensidad (ej: "sales")
            title: Título

        Returns:
            Matriz de datos para heatmap
        """
        try:
            logger.info(f"Generando heatmap: {title}")

            # Crear matriz
            heatmap_data = []
            for item in data:
                heatmap_data.append({
                    "x": str(item.get(x_field)),
                    "y": str(item.get(y_field)),
                    "value": item.get(value_field, 0)
                })

            chart = {
                "type": "heatmap",
                "title": title,
                "data": heatmap_data,
                "options": {
                    "responsive": True,
                    "colorScale": {
                        "min": "#ffffff",
                        "max": "#ff0000"
                    }
                }
            }

            return chart

        except Exception as e:
            logger.error(f"Error generando heatmap: {str(e)}")
            raise

    async def generate_waterfall_chart(
        self,
        categories: List[str],
        values: List[float],
        title: str
    ) -> Dict[str, Any]:
        """
        Genera gráfico waterfall (desglose de cambios)

        Args:
            categories: Categorías (ej: ["Inicio", "Aumento", "Descuento", "Final"])
            values: Valores (positivos o negativos)
            title: Título

        Returns:
            Datos para waterfall chart
        """
        try:
            logger.info(f"Generando waterfall: {title}")

            chart = {
                "type": "waterfall",
                "title": title,
                "data": {
                    "labels": categories,
                    "datasets": [
                        {
                            "data": values,
                            "borderColor": "rgb(100, 100, 100)",
                            "backgroundColor": [
                                "rgba(75, 192, 192, 0.8)" if v > 0 else "rgba(255, 99, 132, 0.8)"
                                for v in values
                            ]
                        }
                    ]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": title
                        }
                    }
                }
            }

            return chart

        except Exception as e:
            logger.error(f"Error generando waterfall: {str(e)}")
            raise

    async def generate_table(
        self,
        data: List[Dict[str, Any]],
        columns: List[str],
        title: str,
        sortable: bool = True,
        filterable: bool = True
    ) -> Dict[str, Any]:
        """
        Genera tabla dinámica filtrable y sorteable

        Args:
            data: Lista de registros
            columns: Columnas a mostrar
            title: Título de la tabla
            sortable: Permitir ordenamiento
            filterable: Permitir filtrado

        Returns:
            Datos para tabla dinámica
        """
        try:
            logger.info(f"Generando tabla: {title}")

            # Filtrar columnas
            table_data = [
                {col: row.get(col) for col in columns}
                for row in data
            ]

            table = {
                "type": "table",
                "title": title,
                "columns": columns,
                "data": table_data,
                "options": {
                    "sortable": sortable,
                    "filterable": filterable,
                    "pagination": {
                        "enabled": True,
                        "itemsPerPage": 20
                    }
                }
            }

            return table

        except Exception as e:
            logger.error(f"Error generando tabla: {str(e)}")
            raise

    @staticmethod
    def format_currency(value: float, currency: str = "S/") -> str:
        """Formatea valor a moneda"""
        return f"{currency} {value:,.2f}"

    @staticmethod
    def format_percentage(value: float) -> str:
        """Formatea valor a porcentaje"""
        return f"{value:.2f}%"

    @staticmethod
    def format_number(value: float, decimals: int = 0) -> str:
        """Formatea número con decimales"""
        if decimals == 0:
            return f"{value:,.0f}"
        return f"{value:,.{decimals}f}"


# Instancia singleton
chart_generator = ChartGenerator()
