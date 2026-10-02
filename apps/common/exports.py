"""Utility functions for exporting portal table data to CSV."""
import csv
from django.http import HttpResponse


def export_as_csv(filename: str, headers: list[str], rows: list[list]) -> HttpResponse:
    """Streams a CSV file download response with Excel-compatible UTF-8 BOM encoding."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    # Write UTF-8 BOM so Excel opens non-ASCII characters without distortion
    response.write("\ufeff")
    
    writer = csv.writer(response)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([str(item) if item is not None else "" for item in row])
    return response
