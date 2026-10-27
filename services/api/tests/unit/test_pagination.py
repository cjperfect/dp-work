import pytest
from pydantic import ValidationError

from src.core.pagination import Page, PageParams


def test_page_offsets_and_totals():
    assert PageParams(page=3, page_size=12).offset == 24
    assert Page[int](item=[1], total=13, page=1, page_size=12).model_dump() == {"item": [1], "total": 13, "page": 1, "page_size": 12}


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 0}, {"page_size": 101}])
def test_page_parameters_have_bounds(params):
    with pytest.raises(ValidationError):
        PageParams(**params)
