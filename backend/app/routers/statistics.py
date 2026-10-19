"""Read-only statistics APIs (Staff/Admin). Periods are Vietnam calendar days, both ends inclusive."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.schemas import (
    CogsStatisticsResponse,
    InventoryStatisticsResponse,
    OrderStatisticsResponse,
    RevenueStatisticsResponse,
    TopProductResponse,
)
from app.services.statistics import StatisticsService
from app.services.statistics_report import StatisticsReportService
from app.schemas.statistics import OrderReportResponse, ReportOptionsResponse, SalesReportResponse

from .dependencies import CurrentActor, InternalOnly, Page, PageSize, get_report_service, get_statistics_service

admin_router = APIRouter(prefix="/admin/statistics", tags=["Thống kê"], dependencies=[InternalOnly])

Statistics = Annotated[StatisticsService, Depends(get_statistics_service)]
Reports = Annotated[StatisticsReportService, Depends(get_report_service)]


@admin_router.get('/report-options', response_model=ReportOptionsResponse)
def report_options(service: Reports, actor: CurrentActor):
    return service.options(actor)


@admin_router.get('/reports/revenue', response_model=SalesReportResponse)
def sales_report(date_from: date, date_to: date, service: Reports, actor: CurrentActor,
                 category_id: UUID | None = None, brand_id: UUID | None = None,
                 product_id: UUID | None = None, page: Page = 1, page_size: PageSize = 10):
    return service.report(actor, 'revenue', date_from, date_to, category_id=category_id,
                          brand_id=brand_id, product_id=product_id, page=page, page_size=page_size)


@admin_router.get('/reports/orders', response_model=OrderReportResponse)
def orders_report(date_from: date, date_to: date, service: Reports, actor: CurrentActor,
                  category_id: UUID | None = None, brand_id: UUID | None = None,
                  product_id: UUID | None = None, page: Page = 1, page_size: PageSize = 10):
    return service.report(actor, 'orders', date_from, date_to, category_id=category_id,
                          brand_id=brand_id, product_id=product_id, page=page, page_size=page_size)


@admin_router.get("/orders", response_model=OrderStatisticsResponse)
def order_statistics(date_from: date, date_to: date, service: Statistics, actor: CurrentActor):
    return service.order_statistics(actor, date_from, date_to)


@admin_router.get("/revenue", response_model=RevenueStatisticsResponse)
def revenue_statistics(date_from: date, date_to: date, service: Statistics, actor: CurrentActor):
    return service.revenue_statistics(actor, date_from, date_to)


@admin_router.get("/cogs", response_model=CogsStatisticsResponse)
def cogs_statistics(date_from: date, date_to: date, service: Statistics, actor: CurrentActor):
    return service.cogs_statistics(actor, date_from, date_to)


@admin_router.get("/top-products", response_model=list[TopProductResponse])
def top_products(date_from: date, date_to: date, service: Statistics, actor: CurrentActor,
                 rank_by: Literal["quantity", "revenue"] = "quantity",
                 limit: Annotated[int, Query(ge=1, le=100)] = 10):
    return service.top_products(actor, date_from, date_to, rank_by=rank_by, limit=limit)


@admin_router.get("/inventory", response_model=InventoryStatisticsResponse)
def inventory_statistics(service: Statistics, actor: CurrentActor, page: Page = 1,
                         page_size: Annotated[int, Query(ge=1, le=200)] = 50):
    return service.inventory_statistics(actor, page=page, page_size=page_size)
