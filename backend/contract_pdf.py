"""PDF of the rental contract accepted in the app, filled with customer and booking data."""
import io
import re
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

_FONTS = os.path.join(os.path.dirname(__file__), "fonts")
pdfmetrics.registerFont(TTFont("Sans", os.path.join(_FONTS, "LiberationSans-Regular.ttf")))
pdfmetrics.registerFont(TTFont("Sans-Bold", os.path.join(_FONTS, "LiberationSans-Bold.ttf")))
TZ = ZoneInfo("Europe/Rome")
DOC_TYPES = {"ci": "Carta d'identità", "patente": "Patente", "passaporto": "Passaporto"}

ST = {
    "title": ParagraphStyle("t", fontName="Sans-Bold", fontSize=13, leading=16, spaceAfter=4),
    "h": ParagraphStyle("h", fontName="Sans-Bold", fontSize=9.5, leading=12, spaceBefore=8, spaceAfter=3),
    "p": ParagraphStyle("p", fontName="Sans", fontSize=8.2, leading=10.5, spaceAfter=2),
    "small": ParagraphStyle("s", fontName="Sans", fontSize=7.5, leading=9.5, textColor=colors.HexColor("#555555")),
    "cell": ParagraphStyle("c", fontName="Sans", fontSize=8.2, leading=10),
    "cellb": ParagraphStyle("cb", fontName="Sans-Bold", fontSize=8.2, leading=10),
}


def _it(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def _ts(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(TZ).strftime("%d/%m/%Y alle %H:%M:%S")


def _grid(rows: list) -> Table:
    data = [[Paragraph(escape(k), ST["cellb"]), Paragraph(escape(str(v or "—")), ST["cell"])] for k, v in rows]
    t = Table(data, colWidths=[48 * mm, 130 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
                           ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F2F2")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t


def build_contract_pdf(bk: dict, contract_lines: list[str]) -> bytes:
    c = bk.get("customer") or {}
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm,
                            bottomMargin=14 * mm, title=f"Contratto noleggio {bk.get('sheet_id') or bk['id'][:8]}")
    head = contract_lines[:3]
    # Sections 1-2 of the sheet are blank forms: we print them filled; the clauses start at section 3.
    start = next((i for i, l in enumerate(contract_lines) if l.startswith("3.")), 3)
    clauses = contract_lines[start:]

    story = [Paragraph(escape(head[0]) if head else "CONTRATTO DI NOLEGGIO", ST["title"])]
    story += [Paragraph(escape(l.replace("________", bk.get("sheet_id") or bk["id"][:8].upper())), ST["small"]) for l in head[1:]]
    story.append(Paragraph("1. DATI DEL CLIENTE / LOCATARIO", ST["h"]))
    story.append(_grid([
        ("Cognome e Nome", c.get("full_name")), ("Codice Fiscale", c.get("tax_code")),
        ("Data di Nascita", _it(c["birth_date"]) if c.get("birth_date") else ""),
        ("Indirizzo e N. Civico", c.get("address")), ("Città e CAP", c.get("city_zip")),
        ("Nazionalità", c.get("nationality")), ("Tipo Documento", DOC_TYPES.get(c.get("doc_type", ""), "")),
        ("Numero Documento", c.get("doc_number")), ("Ente e Scadenza", c.get("doc_issuer_expiry")),
        ("Telefono / Cellulare", bk.get("phone")), ("Indirizzo E-mail", bk.get("user_email")),
        ("Contatto Emergenza", c.get("emergency_contact")),
    ]))
    story.append(Paragraph("2. SPECIFICHE MEZZO E PERIODO DI NOLEGGIO", ST["h"]))
    story.append(_grid([
        ("Modello", f'{bk["bike_name"]} – taglia {bk["size"]}'), ("ID mezzo", bk.get("unit_id")),
        ("Inizio", f'{_it(bk["start"])} ore 09:00'), ("Rientro", f'{_it(bk["end"])} ore 19:00'),
        ("Corrispettivo Noleggio", f'€ {bk["total"]:.2f} (IVA incl.)'),
        ("Pagamento", "Carta (pagato online)" if bk.get("payment_status") == "paid" else "In negozio al ritiro"),
        ("Deposito, accessori, stato mezzo, batteria", "Da compilare al ritiro in negozio"),
    ]))
    for l in clauses:
        heading = bool(re.match(r"^\d\.\s", l)) or l.isupper()
        story.append(Paragraph(escape(l), ST["h"] if heading else ST["p"]))

    story.append(Spacer(1, 6))
    story.append(Paragraph("ACCETTAZIONE ELETTRONICA IN APP", ST["h"]))
    when = _ts(bk["contract_accepted_at"]) if bk.get("contract_accepted_at") else "—"
    story.append(_grid([
        ("Accettato da", f'{c.get("full_name") or bk.get("user_name")} ({bk.get("user_email")})'),
        ("Data e ora", f"{when} (ora italiana)"),
        ("Contratto", "Letto e accettato: SÌ"),
        ("Clausole artt. 1341-1342 c.c.", "Approvazione specifica Sez. 3 e Sez. 4: SÌ"),
        ("Privacy (Reg. UE 2016/679)", "Consenso al trattamento dati: SÌ"),
        ("Versione contratto", bk.get("contract_version")), ("Prenotazione", bk.get("sheet_id") or bk["id"]),
    ]))
    story.append(Spacer(1, 4))
    story.append(Paragraph("Documento generato dall'app Mondo Noleggio. Deposito cauzionale, accessori, stato del mezzo e "
                           "firma per ricevuta vengono completati al momento del ritiro.", ST["small"]))
    doc.build(story)
    return buf.getvalue()
