from math import inf
from urllib.parse import urlencode

from ninja import Schema
from ninja.conf import settings
from ninja.pagination import PaginationBase
from pydantic import Field


class ResultsLimitOffsetPagination(PaginationBase):
    class Input(Schema):
        limit: int = Field(
            settings.PAGINATION_PER_PAGE,
            ge=1,
            le=(
                settings.PAGINATION_MAX_LIMIT
                if settings.PAGINATION_MAX_LIMIT != inf
                else None
            ),
        )
        offset: int = Field(0, ge=0)

    class Output(Schema):
        count: int
        next: str | None
        previous: str | None
        results: list

    items_attribute = "results"

    def _build_page_url(self, request, limit: int, offset: int) -> str:
        query_params = request.GET.copy()
        query_params["limit"] = str(limit)
        query_params["offset"] = str(offset)
        query_string = urlencode(query_params, doseq=True)
        base_url = request.build_absolute_uri(request.path)
        return f"{base_url}?{query_string}" if query_string else base_url

    def paginate_queryset(self, queryset, pagination: Input, request, **params):
        offset = pagination.offset
        limit = min(pagination.limit, settings.PAGINATION_MAX_LIMIT)
        count = self._items_count(queryset)

        next_url = None
        if offset + limit < count:
            next_url = self._build_page_url(request, limit, offset + limit)

        previous_url = None
        if offset > 0:
            previous_url = self._build_page_url(request, limit, max(offset - limit, 0))

        return {
            self.items_attribute: queryset[offset : offset + limit],
            "count": count,
            "next": next_url,
            "previous": previous_url,
        }
