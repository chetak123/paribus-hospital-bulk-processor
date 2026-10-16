import pytest

from app.csv_parser import CSVValidationError, parse_hospital_csv


def test_parses_required_columns_and_optional_phone():
    records = parse_hospital_csv(
        b"name,address,phone\nCity Hospital,MG Road,123\nGeneral Care,HSR,\n"
    )
    assert len(records) == 2
    assert records[0].name == "City Hospital"
    assert records[1].phone is None


@pytest.mark.parametrize(
    "contents",
    [
        b"",
        b"name,phone\nHospital,123\n",
        b"name,address\n,MG Road\n",
        b"name,address\nHospital,\n",
    ],
)
def test_rejects_invalid_csv(contents):
    with pytest.raises(CSVValidationError):
        parse_hospital_csv(contents)


def test_rejects_more_than_twenty_records():
    rows = ["name,address"] + [
        f"Hospital {index},Address {index}" for index in range(21)
    ]
    with pytest.raises(CSVValidationError, match="maximum allowed is 20"):
        parse_hospital_csv(("\n".join(rows) + "\n").encode())
