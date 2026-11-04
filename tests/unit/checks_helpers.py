"""Record builder for check tests (does not depend on the ingest module)."""
from dqa.models import Context, NormView, Record
from dqa.normalize import normalize_mpn, normalize_uom, tokenize

CTX = Context(batch_id="b_1")


def rec(row=1, item_id="1", source="ERP-A", desc="SKF Bearing 6205 ZZ", mfr="SKF",
        mpn="6205-ZZ", cat="Mechanical", uom="EA", key=None):
    raw = {"item_id": item_id, "item_description": desc, "manufacturer": mfr,
           "manufacturer_part_number": mpn, "category": cat, "unit_of_measure": uom,
           "source_system": source}
    return Record(
        row_number=row, record_key=key or f"{source}:{item_id}", source_system=source,
        item_id=item_id, item_description=desc, manufacturer=mfr,
        manufacturer_part_number=mpn, category=cat, unit_of_measure=uom, raw=raw,
        norm=NormView(description_tokens=tokenize(desc), mpn_key=normalize_mpn(mpn),
                      uom_key=normalize_uom(uom)),
    )
