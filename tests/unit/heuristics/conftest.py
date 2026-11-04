import pytest

from dqa.models import Record


@pytest.fixture
def rec():
    def make(item_id="1", source="ERP-A", desc="SKF Bearing 6205 ZZ", mfr="SKF", mpn="6205-ZZ",
             cat="Mechanical", uom="EA", row=1, key=None):
        raw = {"item_id": item_id, "item_description": desc, "manufacturer": mfr,
               "manufacturer_part_number": mpn, "category": cat, "unit_of_measure": uom,
               "source_system": source}
        return Record(row_number=row, record_key=key or f"{source}:{item_id}", raw=raw, **raw)

    return make
