"""Helpers shared by the scripts that write ATR_Tracker_Dashboard.xlsx."""


def ensure_excel_headers(ws, headers):
    """Fill in any missing header cells on an existing worksheet.

    Headers are normally written only when a sheet is created. A workbook that
    predates a newly added column (High/Low/Volume) would otherwise keep a
    headerless column, which pandas later reads as 'Unnamed: N'.
    Returns the number of header cells that were added.
    """
    added = 0
    for col, header in enumerate(headers, 1):
        if ws.cell(row=1, column=col).value is None:
            ws.cell(row=1, column=col, value=header)
            added += 1
    return added
