"""Build the wedding accommodation spreadsheet.

Usage: python build.py geo.json out.xlsx
"""
import json
import sys

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

CHECKED_ON = "15/11/2026"
CHATEAU_TO_CHURCH = (7.4, 9)  # km, min (OSRM)
CONTACT = "Contact Emma"

WINE = "8E5A66"
ROSE = "F3E6E9"
GOLD = "FFF4D6"
GREY = "D9D9D9"
HEAD = Font(bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor=WINE)
EDIT_FILL = PatternFill("solid", fgColor=GOLD)
SPECIAL_FILL = PatternFill("solid", fgColor=ROSE)
WRAP = Alignment(wrap_text=True, vertical="top")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

AVAIL_LABEL = {
    "available": "Free on 7 Aug (online calendar)",
    "calendar_not_open": "Calendar not open yet",
    "no_online_calendar": "Ask the owner",
    "unknown": "Check the link or ask the owner",
}

COLUMNS = [  # (header, width)
    ("Status ✏️", 14), ("Taken by ✏️", 18), ("Name", 30), ("Type", 16), ("Village", 20),
    ("Aug 7 availability", 22), ("Km to château", 9), ("Km to church", 9), ("Min to church", 9),
    ("Sleeps", 8), ("Bedrooms", 9), ("Beds", 26), ("Bathrooms", 10),
    ("Last seen price (€)", 11), ("Price unit", 18), ("Price note", 30), ("Checked on", 11),
    ("Link", 34), ("Phone", 16), ("Email", 28), ("Notes", 40),
]


def pavillon_rows():
    km, mins = CHATEAU_TO_CHURCH
    common = dict(type="Rooms (château grounds)", village="Saint-Pourçain-sur-Besbre",
                  avail="Book through Emma", km_chateau=0.1, km_church=km, min_church=mins,
                  checked=CHECKED_ON, link="", phone="", email="")
    return [
        dict(common, name="Pavillon de Chasse – room with private bathroom & WC (2 rooms)",
             sleeps=4, bedrooms=2, beds="1 room with a 160 cm double, 1 room with twin beds",
             bathrooms="1 per room", price=285, unit="per room, 2 nights, 2 people",
             note="Or 190 € for 1 night. Sheets, towels, beds made.",
             notes="Hunting lodge a few steps from the château; lounge with stove, kitchenette, "
                   "ping-pong & table football. Contact Emma to book."),
        dict(common, name="Pavillon de Chasse – room with washbasin (6 rooms)",
             sleeps=12, bedrooms=6, beds="4 rooms with a 160 cm double, 2 rooms with twin beds",
             bathrooms="Shared: 3 showers + 2 WC on the landing", price=210,
             unit="per room, 2 nights, 2 people",
             note="Or 150 € for 1 night. Sheets, towels, beds made.",
             notes="Same building as above. Contact Emma to book."),
    ]


def listing_row(l):
    return dict(
        name=l["name"], type=l.get("type", ""), village=l.get("village", ""),
        avail=AVAIL_LABEL[l["aug7_status"]],
        km_chateau=l.get("km_chateau"), km_church=l.get("km_church"), min_church=l.get("min_church"),
        sleeps=l.get("sleeps"), bedrooms=l.get("bedrooms"), beds=l.get("beds") or "",
        bathrooms=l.get("bathrooms"), price=l.get("price_eur"), unit=l.get("price_unit") or "",
        note=l.get("price_note") or "", checked=CHECKED_ON if l.get("price_eur") else "",
        link=l.get("link") or "", phone=l.get("phone") or "", email=l.get("email") or "",
        notes=l.get("notes") or "",
    )


def header(ws, row, titles, fill=HEAD_FILL):
    for c, t in enumerate(titles, 1):
        cell = ws.cell(row=row, column=c, value=t)
        cell.font, cell.fill, cell.border = HEAD, fill, BOX
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")


def build_accommodation(wb, listings):
    ws = wb.create_sheet("Accommodation")
    header(ws, 1, [c for c, _ in COLUMNS])
    ws.row_dimensions[1].height = 34
    for i, (_, w) in enumerate(COLUMNS, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    keep = [l for l in listings if l["listing_status"] == "active" and l["aug7_status"] != "booked"]
    keep.sort(key=lambda l: (l.get("km_church") is None, l.get("km_church") or 0, l["name"]))
    rows = pavillon_rows() + [listing_row(l) for l in keep]
    n_special = len(pavillon_rows())

    for r, d in enumerate(rows, 2):
        special = r - 2 < n_special
        vals = [CONTACT if special else "Available", "", d["name"], d["type"], d["village"], d["avail"],
                d["km_chateau"], d["km_church"], d["min_church"], d["sleeps"], d["bedrooms"], d["beds"],
                d["bathrooms"], d["price"], d["unit"], d["note"], d["checked"], d["link"], d["phone"],
                d["email"], d["notes"]]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.alignment, cell.border = WRAP, BOX
            if special:
                cell.fill = SPECIAL_FILL
        if not special:
            ws.cell(row=r, column=1).fill = EDIT_FILL
            ws.cell(row=r, column=2).fill = EDIT_FILL
        ws.cell(row=r, column=3).font = Font(bold=True)
        ws.cell(row=r, column=14).number_format = '#,##0 "€"'
        if d["link"].startswith("http"):
            ws.cell(row=r, column=18).hyperlink = d["link"]
            ws.cell(row=r, column=18).font = Font(color="0563C1", underline="single")

    last = len(rows) + 1
    first_editable = 2 + n_special
    dv = DataValidation(type="list", formula1='"Available,Taken"', allow_blank=False,
                        showErrorMessage=True, errorTitle="Status",
                        error="Choose Available or Taken from the list.")
    dv.add(f"A{first_editable}:A{last}")
    ws.add_data_validation(dv)
    ws.conditional_formatting.add(
        f"A2:{get_column_letter(len(COLUMNS))}{last}",
        FormulaRule(formula=['$A2="Taken"'], fill=PatternFill("solid", fgColor=GREY),
                    font=Font(color="808080", strike=True)))
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{last}"
    return keep, [l for l in listings if l not in keep]


# (floor, bedroom, beds, max people)
JARGEOTS = [
    ("Ground floor", "Bedroom 1", "1 double 160 cm", 2),
    ("Ground floor", "Bedroom 2", "1 double 160 cm", 2),
    ("1st floor", "Bedroom 3", "1 double 160 cm", 2),
    ("1st floor", "Bedroom 4 (family)", "1 double 160 cm + 2 singles 90 cm", 4),
]
MOULIN = [
    ("Ground floor", "Bedroom 1", "1 double 160 cm", 2),
    ("Ground floor", "Bedroom 2", "1 double 160 cm", 2),
    ("Ground floor", "Bedroom 3", "2 singles", 2),
    ("1st floor", "Bedroom 4", "1 double 160 cm", 2),
    ("1st floor", "Bedroom 5 (family)", "1 double 160 cm + 1 single 90 cm", 3),
    ("1st floor", "Bedroom 6 (family)", "2 singles (can join as a double) + 1 single 90 cm", 3),
]


def build_shared(wb):
    ws = wb.create_sheet("Beauvoir gîtes (shared)")
    for col, w in zip("ABCDEFG", (14, 22, 40, 11, 40, 10, 4)):
        ws.column_dimensions[col].width = w
    ws["A1"] = "Beauvoir gîtes: let's fill them together"
    ws["A1"].font = Font(bold=True, size=14, color=WINE)
    ws["A2"] = ("These two houses on the château grounds are rented as a whole house only (2 nights minimum). "
                "Write your name(s) next to the room you'd like and how many people you are. "
                "Signing up is a sign of interest, not a booking: once a house has enough people, "
                "Emma books it and splits the cost. Please don't book these houses yourself.")
    ws["A2"].alignment = WRAP
    ws.merge_cells("A2:F2")
    ws.row_dimensions[2].height = 62

    row = 4
    blocks = [
        ("Gîte Cottage des Jargeots", 10, 4, "2 bathrooms + 2 separate WCs", 1200, JARGEOTS,
         "Equipped kitchen, wood stove, covered terrace with plancha, garden, washer & dryer, baby cot."),
        ("Gîte du Moulin", 14, 6, "3 bathrooms + 3 separate WCs", 1600, MOULIN,
         "Riverside garden with a view of the château, equipped kitchen, wood stove, covered terrace, "
         "TV & games room, washer & dryer, baby cot & high chair."),
    ]
    for name, cap, bedrooms, baths, price, rooms, extras in blocks:
        ws.cell(row=row, column=1, value=name).font = Font(bold=True, size=13, color="FFFFFF")
        for c in range(1, 7):
            ws.cell(row=row, column=c).fill = HEAD_FILL
        row += 1
        info = (f"Sleeps {cap} · {bedrooms} bedrooms · {baths} · {price:,} € for the whole house, "
                f"2 nights minimum · sheets & towels provided. {extras}").replace(",", " ", 1)
        ws.cell(row=row, column=1, value=info).alignment = WRAP
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
        ws.row_dimensions[row].height = 46
        row += 1
        header(ws, row, ["Floor", "Bedroom", "Beds", "Max people", "Guest names ✏️", "People ✏️"])
        row += 1
        first = row
        for floor, room, beds, mx in rooms:
            for c, v in enumerate([floor, room, beds, mx, "", None], 1):
                cell = ws.cell(row=row, column=c, value=v)
                cell.border, cell.alignment = BOX, WRAP
            ws.cell(row=row, column=5).fill = EDIT_FILL
            ws.cell(row=row, column=6).fill = EDIT_FILL
            dv = DataValidation(type="whole", operator="between", formula1="0", formula2=str(mx),
                                showErrorMessage=True, errorTitle="People",
                                error=f"This room sleeps at most {mx}.")
            dv.add(f"F{row}")
            ws.add_data_validation(dv)
            row += 1
        lastr = row - 1
        summary = [
            ("People signed up", f"=SUM(F{first}:F{lastr})", None),
            ("Places left", f"={cap}-SUM(F{first}:F{lastr})", None),
            ("Cost per person (2 nights), with current sign-ups",
             f'=IF(SUM(F{first}:F{lastr})>0,{price}/SUM(F{first}:F{lastr}),"–")', '#,##0 "€"'),
            ("Cost per person (2 nights) when full", f"={price}/{cap}", '#,##0 "€"'),
            ("Status", f'=IF(SUM(F{first}:F{lastr})>={cap},"Full: Emma will book it",'
                       f'SUM(F{first}:F{lastr})&" of {cap} places filled")', None),
        ]
        for label, formula, fmt in summary:
            ws.cell(row=row, column=5, value=label).font = Font(bold=True)
            ws.cell(row=row, column=5).alignment = Alignment(horizontal="right", wrap_text=True)
            cell = ws.cell(row=row, column=6, value=formula)
            cell.font, cell.fill = Font(bold=True), SPECIAL_FILL
            if fmt:
                cell.number_format = fmt
            row += 1
        row += 2
    ws.freeze_panes = "A4"


def build_readme(wb):
    ws = wb.active
    ws.title = "Read me"
    ws.column_dimensions["A"].width = 110
    lines = [
        ("Where to stay: Theodor & Emma's wedding", Font(bold=True, size=16, color=WINE)),
        ("Saturday 7 August 2027 · Église Saint-Joseph, Dompierre-sur-Besbre · Château de Beauvoir", Font(italic=True)),
        ("", None),
        ("HOW TO USE THIS SHEET", Font(bold=True, color=WINE)),
        ("• Tab 'Accommodation': places near the château and the church, nearest to the church first. "
         "Use the filters in the header row to sort or hide rows.", None),
        ("• You can only edit the yellow columns. Everything else is locked.", None),
        ("• Once you've ACTUALLY BOOKED a place, set Status to 'Taken' and write your name in 'Taken by'. "
         "The row turns grey so nobody else wastes time on it. If the place still has room "
         "(a hotel, for example), leave it 'Available' and just add your name.", None),
        ("• If you cancel, set it back to 'Available' and clear your name. Please never change someone else's row.", None),
        ("", None),
        ("AUG 7 AVAILABILITY COLUMN", Font(bold=True, color=WINE)),
        ("• Free on 7 Aug (online calendar): the booking calendar showed 7 August free when we checked. Book soon!", None),
        ("• Calendar not open yet: the calendar doesn't go as far as August 2027 yet. Check later or contact the owner.", None),
        ("• Check the link or ask the owner: there is an online calendar, but we couldn't read it. Check the link yourself.", None),
        ("• Ask the owner: no online calendar. Call or email.", None),
        ("Places already booked on 7 August, closed, or not found online are in the last tab, 'Not listed (for reference)'.", None),
        (f"Prices are the last ones we saw online (checked on {CHECKED_ON}). Always confirm with the owner, "
         "and check the 'Price unit' column: some places rent per night, others per weekend or per week.", None),
        ("", None),
        ("SPECIAL PLACES ON THE CHÂTEAU GROUNDS", Font(bold=True, color=WINE)),
        ("• Pavillon de Chasse (hunting lodge, pink rows at the top): 8 rooms, up to 16 guests. "
         "Don't book online or mark them here. Contact Emma, who'll confirm and send you the château's payment link.", None),
        ("• Gîte Cottage des Jargeots (10 people) and Gîte du Moulin (14 people): rented as whole houses only. "
         "See the tab 'Beauvoir gîtes (shared)' to sign up room by room. Emma books once a house is full enough.", None),
        ("", None),
        ("Contact Emma: emma.chirlomez@gmail.com · +40 720 410 905", Font(bold=True)),
        ("Tip: many gîtes are listed with Gîtes de France Allier (+33 4 82 75 68 55). "
         "Give them the reference number from the Notes column.", None),
    ]
    for i, (text, font) in enumerate(lines, 1):
        c = ws.cell(row=i, column=1, value=text)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if font:
            c.font = font


def build_excluded(wb, excluded):
    ws = wb.create_sheet("Not listed (for reference)")
    header(ws, 1, ["Name", "Village", "Why not listed", "Details", "Link"])
    for col, w in zip("ABCDE", (32, 22, 18, 70, 40)):
        ws.column_dimensions[col].width = w
    why = {"closed": "Closed / no longer rented", "not_found": "Not found online", "booked": "Booked on 7 Aug"}
    excluded = sorted(excluded, key=lambda l: (l.get("village", ""), l["name"]))
    for r, l in enumerate(excluded, 2):
        reason = "booked" if l["listing_status"] == "active" else l["listing_status"]
        detail = l.get("aug7_detail") if reason == "booked" else (l.get("notes") or "")
        for c, v in enumerate([l["name"], l.get("village", ""), why[reason], detail, l.get("link", "")], 1):
            ws.cell(row=r, column=c, value=v).alignment = WRAP
    ws.freeze_panes = "A2"


def main(src, dst):
    listings = json.load(open(src))
    wb = Workbook()
    build_readme(wb)
    keep, excluded = build_accommodation(wb, listings)
    build_shared(wb)
    build_excluded(wb, excluded)
    wb.save(dst)
    from collections import Counter
    print(f"listed {len(keep)}, excluded {len(excluded)}")
    print("availability:", Counter(l["aug7_status"] for l in keep))
    print("excluded:", Counter((l["listing_status"], l["aug7_status"]) for l in excluded))


if __name__ == "__main__":
    main(*sys.argv[1:3])
