"""Invoice PDF generation service."""
import io
import logging
from xml.sax.saxutils import escape

from django.conf import settings
from django.template.loader import render_to_string

from apps.common.models import get_platform_settings
from apps.common.theme import get_portal_colors

logger = logging.getLogger("payments")


class InvoiceService:
    """Generates PDF invoices and stores them in object storage."""

    @staticmethod
    def generate_pdf(invoice) -> str:
        """Generate invoice PDF and upload to storage. Returns storage key."""
        try:
            # Generate PDF (WeasyPrint if available, otherwise ReportLab)
            pdf_bytes = InvoiceService._build_pdf(invoice)

            # Upload to storage
            storage_key = f"invoices/{invoice.invoice_number}.pdf"
            from apps.storage.service import get_storage_service
            storage = get_storage_service()
            storage.upload_file(
                key=storage_key,
                file_obj=io.BytesIO(pdf_bytes),
                content_type="application/pdf",
                metadata={"invoice_number": invoice.invoice_number},
            )

            invoice.storage_key = storage_key
            invoice.save(update_fields=["storage_key"])
            return storage_key

        except Exception as exc:
            logger.error("Invoice PDF generation failed: %s", exc)
            return ""

    @staticmethod
    def _build_pdf(invoice) -> bytes:
        """Try WeasyPrint first; fallback to ReportLab."""
        try:
            from weasyprint import HTML
            branding = get_platform_settings()
            logo = branding.get("logo") if isinstance(branding, dict) else branding.logo
            website_url = branding.get("website_url") if isinstance(branding, dict) else branding.website_url
            portal_colors = get_portal_colors(branding)
            html_content = render_to_string("payments/invoice_pdf.html", {
                "invoice": invoice,
                "order": invoice.order,
                "PLATFORM_NAME": branding.get("name") if isinstance(branding, dict) else branding.name,
                "PLATFORM_LOGO_URL": logo.url if logo else "",
                "branding": branding,
                "portal_colors": portal_colors,
                "platform_url": getattr(settings, "PLATFORM_URL", "http://localhost:8000"),
            })
            return HTML(
                string=html_content,
                base_url=website_url or getattr(settings, "PLATFORM_URL", "") or None,
            ).write_pdf()
        except (ImportError, Exception) as exc:
            logger.info("WeasyPrint unavailable (%s), rendering with ReportLab", exc)
            return InvoiceService._generate_with_reportlab(invoice)

    @staticmethod
    def _generate_with_weasyprint(html_content: str, invoice=None) -> bytes:
        """Generate PDF using WeasyPrint with graceful fallback."""
        try:
            from weasyprint import HTML
            return HTML(string=html_content).write_pdf()
        except (ImportError, Exception) as exc:
            logger.warning("WeasyPrint failed (%s), falling back to ReportLab", exc)
            if invoice:
                return InvoiceService._generate_with_reportlab(invoice)
            return b""

    @staticmethod
    def _generate_with_reportlab(invoice) -> bytes:
        """Generate high-quality, professional branded PDF invoice using ReportLab."""
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.platypus import HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                leftMargin=40,
                rightMargin=40,
                topMargin=40,
                bottomMargin=40,
            )

            styles = getSampleStyleSheet()

            branding = get_platform_settings()
            portal_colors = get_portal_colors(branding)
            primary = portal_colors["primary"]
            tagline = branding.get("tagline", "") if isinstance(branding, dict) else branding.tagline
            legal_name = branding.get("legal_name", "") if isinstance(branding, dict) else branding.legal_name
            billing_address = branding.get("billing_address", "") if isinstance(branding, dict) else branding.billing_address
            tax_number = branding.get("tax_registration_number", "") if isinstance(branding, dict) else branding.tax_registration_number
            invoice_footer = branding.get("invoice_footer", "") if isinstance(branding, dict) else branding.invoice_footer
            primary_color = colors.HexColor(primary)
            muted_hex = portal_colors["invoice_muted_text"].upper()
            success_hex = portal_colors["success"].upper()
            dark_color = colors.HexColor(portal_colors["invoice_text"])
            muted_color = colors.HexColor(portal_colors["invoice_muted_text"])
            light_bg = colors.HexColor(portal_colors["invoice_surface"])
            border_color = colors.HexColor(portal_colors["invoice_border"])
            subtle_border = colors.HexColor(portal_colors["invoice_border"])

            title_style = ParagraphStyle(
                "PlatformTitle",
                parent=styles["Normal"],
                fontName="Helvetica-Bold",
                fontSize=22,
                leading=26,
                textColor=primary_color,
            )
            invoice_title_style = ParagraphStyle(
                "InvoiceTitle",
                parent=styles["Normal"],
                fontName="Helvetica-Bold",
                fontSize=18,
                leading=22,
                alignment=2,
                textColor=dark_color,
            )
            body_normal = ParagraphStyle(
                "BodyNormal",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=9,
                leading=14,
                textColor=dark_color,
            )
            body_right = ParagraphStyle(
                "BodyRight",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=9,
                leading=14,
                alignment=2,
                textColor=dark_color,
            )
            table_header = ParagraphStyle(
                "TableHeader",
                parent=styles["Normal"],
                fontName="Helvetica-Bold",
                fontSize=9,
                leading=12,
                textColor=dark_color,
            )
            table_header_right = ParagraphStyle(
                "TableHeaderRight",
                parent=table_header,
                alignment=2,
            )
            table_cell = ParagraphStyle(
                "TableCell",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=9,
                leading=13,
                textColor=dark_color,
            )
            table_cell_right = ParagraphStyle(
                "TableCellRight",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=9,
                leading=13,
                alignment=2,
                textColor=dark_color,
            )
            total_bold = ParagraphStyle(
                "TotalBold",
                parent=styles["Normal"],
                fontName="Helvetica-Bold",
                fontSize=12,
                leading=16,
                alignment=2,
                textColor=primary_color,
            )
            footer_style = ParagraphStyle(
                "FooterText",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=8,
                leading=12,
                alignment=1,
                textColor=muted_color,
            )

            order = getattr(invoice, "order", None)
            currency = getattr(order, "currency", "INR") if order else getattr(invoice, "currency", "INR")
            platform_name = branding.get("name") if isinstance(branding, dict) else branding.name

            # Format invoice date
            date_val = getattr(invoice, "issued_at", None) or getattr(invoice, "created_at", None)
            date_str = date_val.strftime("%B %d, %Y") if date_val else "N/A"

            elements = []

            # 1. Header Row: Platform info & Tax Invoice Title
            header_data = [
                [
                    Paragraph(f"<b>{escape(platform_name)}</b><br/><font color='{muted_hex}' size='9'>{escape(tagline)}</font>", title_style),
                    Paragraph(f"<b>TAX INVOICE</b><br/><font color='{muted_hex}' size='9'>#{invoice.invoice_number}<br/>Date: {date_str}</font>", invoice_title_style),
                ]
            ]
            logo_field = branding.get("logo") if isinstance(branding, dict) else branding.logo
            if logo_field:
                try:
                    with logo_field.open("rb") as logo_file:
                        logo_image = Image(io.BytesIO(logo_file.read()), width=160, height=56, kind="proportional")
                    header_data[0][0] = Table([
                        [logo_image],
                        [Paragraph(
                            f"<b>{escape(platform_name)}</b><br/><font color='{muted_hex}' size='9'>{escape(tagline)}</font>",
                            title_style,
                        )],
                    ], colWidths=[290])
                except (OSError, ValueError):
                    pass
            header_table = Table(header_data, colWidths=[300, 232])
            header_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
            ]))
            elements.append(header_table)
            company_lines = [value for value in (legal_name, billing_address, f"Tax ID: {tax_number}" if tax_number else "") if value]
            if company_lines:
                elements.append(Paragraph("<br/>".join(escape(value) for value in company_lines), body_normal))
                elements.append(Spacer(1, 8))
            elements.append(Spacer(1, 14))
            elements.append(HRFlowable(width="100%", thickness=2, color=primary_color, spaceAfter=18, spaceBefore=0))

            # 2. Customer & Payment Details
            if order and order.user:
                customer_name = order.billing_name or getattr(order.user, "full_name", "") or order.user.email
                customer_email = order.billing_email or order.user.email
                user_id = str(order.user.id)[:8]
            else:
                customer_name = "Valued Learner"
                customer_email = ""
                user_id = "N/A"

            order_num = getattr(order, "order_number", "N/A") if order else "N/A"
            tx_id = (order.payment_transaction_id or "Prepaid / Verified") if order else "Verified"
            status_text = (order.status.upper() if order else "PAID")

            details_data = [
                [
                    Paragraph(f"<b>Billed To:</b><br/>{customer_name}<br/>{customer_email}<br/>User Ref: {user_id}", body_normal),
                    Paragraph(f"<b>Payment Reference:</b><br/>Order Ref: {order_num}<br/>Transaction ID: {tx_id}<br/>Payment Status: <b><font color='{success_hex}'>{status_text}</font></b>", body_right),
                ]
            ]
            details_table = Table(details_data, colWidths=[266, 266])
            details_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
            ]))
            elements.append(details_table)
            elements.append(Spacer(1, 15))

            # 3. Items Table
            items_data = [
                [
                    Paragraph("<b>Course Item</b>", table_header),
                    Paragraph("<b>Unit Price</b>", table_header_right),
                    Paragraph("<b>Discount</b>", table_header_right),
                    Paragraph("<b>Amount</b>", table_header_right),
                ]
            ]

            order_items = list(order.items.all()) if order else []
            if order_items:
                for item in order_items:
                    items_data.append([
                        Paragraph(f"<b>{escape(item.course_title)}</b>", table_cell),
                        Paragraph(f"{currency} {item.unit_price:,.2f}", table_cell_right),
                        Paragraph(f"{currency} {item.discount_amount:,.2f}", table_cell_right),
                        Paragraph(f"{currency} {item.final_price:,.2f}", table_cell_right),
                    ])
            else:
                items_data.append([
                    Paragraph("<b>Course Enrollment & Lifetime Access</b>", table_cell),
                    Paragraph(f"{currency} {invoice.total:,.2f}", table_cell_right),
                    Paragraph(f"{currency} 0.00", table_cell_right),
                    Paragraph(f"{currency} {invoice.total:,.2f}", table_cell_right),
                ])

            items_table = Table(items_data, colWidths=[272, 85, 85, 90])
            items_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), light_bg),
                ("LINEBELOW", (0, 0), (-1, 0), 1.5, border_color),
                ("LINEBELOW", (0, 1), (-1, -1), 0.5, subtle_border),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            elements.append(items_table)
            elements.append(Spacer(1, 15))

            # 4. Totals Box
            subtotal = getattr(order, "subtotal", invoice.total) if order else invoice.total
            discount = getattr(order, "discount_amount", 0) if order else 0
            tax = getattr(order, "tax_amount", invoice.tax_amount) if order else invoice.tax_amount
            total = getattr(order, "total", invoice.total) if order else invoice.total

            totals_data = [
                [Paragraph("Subtotal:", table_cell_right), Paragraph(f"{currency} {subtotal:,.2f}", table_cell_right)],
            ]
            if discount and discount > 0:
                totals_data.append([
                    Paragraph("Coupon Discount:", table_cell_right),
                    Paragraph(f"<font color='{success_hex}'>-{currency} {discount:,.2f}</font>", table_cell_right),
                ])
            if tax and tax > 0:
                totals_data.append([
                    Paragraph("Tax / GST:", table_cell_right),
                    Paragraph(f"{currency} {tax:,.2f}", table_cell_right),
                ])
            totals_data.append([
                Paragraph("<b>Total Paid:</b>", total_bold),
                Paragraph(f"<b>{currency} {total:,.2f}</b>", total_bold),
            ])

            totals_table = Table(totals_data, colWidths=[120, 110])
            totals_table.setStyle(TableStyle([
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEABOVE", (0, len(totals_data) - 1), (-1, len(totals_data) - 1), 1.5, primary_color),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))

            wrapper_table = Table([[Paragraph("", body_normal), totals_table]], colWidths=[302, 230])
            wrapper_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]))
            elements.append(wrapper_table)
            elements.append(Spacer(1, 40))

            # 5. Footer Notes
            elements.append(HRFlowable(width="100%", thickness=0.5, color=subtle_border, spaceAfter=15, spaceBefore=0))
            elements.append(Paragraph(
                f"{escape(invoice_footer or f'Thank you for learning with {platform_name}.')}<br/>"
                "This is an official computer-generated tax invoice and requires no physical signature.<br/>"
                "For inquiries, billing support, or queries, please visit your account dashboard.",
                footer_style,
            ))

            doc.build(elements)
            return buffer.getvalue()

        except Exception as exc:
            logger.error("ReportLab generation error: %s", exc)
            return b""

    @staticmethod
    def get_download_url(invoice) -> str:
        """Get a signed URL to download the invoice."""
        if not invoice.storage_key:
            return ""
        from apps.storage.service import get_storage_service
        storage = get_storage_service()
        return storage.generate_signed_url(
            key=invoice.storage_key,
            expiry_seconds=3600,
            response_content_type="application/pdf",
            download_filename=f"Invoice-{invoice.invoice_number}.pdf",
        )
