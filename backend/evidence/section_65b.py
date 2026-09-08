"""
Certificate under Section 65B of the Indian Evidence Act, 1872 / Section 63 BSA, 2023.
Produces legally binding evidentiary certificates for electronic records
collected by the Punjab Police Drug Intelligence System for court prosecution.
"""

from typing import Dict, Any, List
from datetime import datetime
import uuid


def generate_section_65b_certificate(
    investigator_name: str,
    investigator_badge: str,
    department: str,
    case_fir_number: str,
    evidence_records: List[Dict[str, Any]]
) -> str:
    """Generate formal legal electronic record certificate."""
    cert_id = f"SEC65B-{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.utcnow().strftime("%d-%m-%Y %H:%M:%S UTC")

    evidence_table_rows = ""
    for idx, rec in enumerate(evidence_records, 1):
        evidence_table_rows += f"""
        <tr>
            <td>{idx}</td>
            <td>{rec.get('source_type', 'ELECTRONIC_INTERCEPT')}</td>
            <td><code>{rec.get('source_url', 'N/A')}</code></td>
            <td><code style="font-size: 10px;">{rec.get('sha256_hash', 'N/A')}</code></td>
            <td>{rec.get('created_at', timestamp)}</td>
        </tr>
        """

    certificate_text = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Section 65B Certificate - {cert_id}</title>
        <style>
            body {{ font-family: 'Times New Roman', Times, serif; margin: 40px; color: #111; line-height: 1.5; }}
            .emblem {{ text-align: center; font-weight: bold; font-size: 16px; margin-bottom: 5px; }}
            .sub-emblem {{ text-align: center; font-size: 13px; margin-bottom: 25px; border-bottom: 2px solid #000; padding-bottom: 10px; }}
            h2 {{ text-align: center; text-decoration: underline; font-size: 15px; margin-bottom: 20px; }}
            p {{ font-size: 13px; text-align: justify; margin-bottom: 12px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; margin-bottom: 20px; font-size: 11px; }}
            th, td {{ border: 1px solid #333; padding: 6px; text-align: left; }}
            th {{ background: #f0f0f0; }}
            .signature-block {{ margin-top: 50px; display: flex; justify-content: space-between; }}
            .seal {{ border: 2px dashed #666; width: 150px; height: 80px; text-align: center; line-height: 80px; color: #666; font-size: 11px; }}
        </style>
    </head>
    <body>
        <div class="emblem">GOVERNMENT OF PUNJAB &bull; DEPARTMENT OF POLICE</div>
        <div class="sub-emblem">STATE NARCOTICS CONTROL BUREAU & CYBER CRIME DIVISION</div>

        <h2>CERTIFICATE UNDER SECTION 65B OF THE INDIAN EVIDENCE ACT, 1872<br>(CORRESPONDING TO SECTION 63 OF BHARATIYA SAKSHYA ADHINIYAM, 2023)</h2>

        <p>
            I, <strong>{investigator_name}</strong>, holding Badge No. <strong>{investigator_badge}</strong>, 
            serving in <strong>{department}</strong>, hereby solemnly affirm and certify as follows:
        </p>

        <p>
            1. That I am the designated Cyber Forensic Investigator in charge of lawful digital intelligence collection 
            pertaining to Case / FIR No. <strong>{case_fir_number}</strong>.
        </p>

        <p>
            2. That the electronic records tabulated below were produced by the Punjab Police Automated Dark Web & 
            Encrypted Platform Intelligence System during its lawful, routine, and uncompromised operation.
        </p>

        <p>
            3. That throughout the period of collection, the computer systems, proxy nodes, and Tor routing servers 
            were operating properly. There was no malfunction that could have affected the contents of the electronic records 
            or the truth of their representations.
        </p>

        <p>
            4. That cryptographic hash sums (SHA-256) were computed immediately at the point of ingestion and remain 
            unaltered, certifying full chain of custody integrity:
        </p>

        <table>
            <thead>
                <tr>
                    <th>S.No</th>
                    <th>Source Type</th>
                    <th>Target / Source Identifier</th>
                    <th>SHA-256 Hash Digest</th>
                    <th>Timestamp (UTC)</th>
                </tr>
            </thead>
            <tbody>
                {evidence_table_rows}
            </tbody>
        </table>

        <p>
            5. To the best of my knowledge and belief, the information contained herein is true, correct, and derived 
            directly from the electronic evidence repository.
        </p>

        <div class="signature-block">
            <div>
                <br><br>
                _______________________________________<br>
                <strong>Signature of Certifying Officer</strong><br>
                Name: {investigator_name}<br>
                Badge: {investigator_badge}<br>
                Date: {timestamp}
            </div>
            <div class="seal">
                OFFICIAL SEAL
            </div>
        </div>
    </body>
    </html>
    """
    return certificate_text
