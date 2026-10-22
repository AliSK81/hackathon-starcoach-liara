"""Custom domains: Liara API calls plus the registrar steps the user must do themself (research 04 B)."""

from __future__ import annotations

from .liara import LiaraClient, _q

LIARA_NS = ["ns1.liara.zone", "ns2.liara.zone"]  # research 04 B.5: read live from the zone API when possible


def list_domains(client: LiaraClient, app: str) -> list[dict]:
    items = client.request("GET", "/v1/domains", params={"project": app}).get("domains", [])
    return [{"id": d.get("_id"), "name": d.get("name"), "status": d.get("status"),
             "ssl": d.get("certificatesStatus"), "cname_target": d.get("CNameRecord")} for d in items]


def add_domain(client: LiaraClient, app: str, domain: str) -> dict:
    created = client.request("POST", "/v1/domains", body={"name": domain, "project": app, "type": "PROJECT"})
    domain_id = (created.get("domain") or {}).get("_id", "")
    return {"id": domain_id, **check_domain(client, domain_id)}


def check_domain(client: LiaraClient, domain_id: str) -> dict:
    d = client.request("GET", f"/v1/domains/{_q(domain_id)}/check").get("domain", {})
    return {"name": d.get("name"), "status": d.get("status"), "ssl": d.get("certificatesStatus"),
            "cname_target": d.get("CNameRecord"), "txt_verification": d.get("verificationCode")}


def enable_ssl(client: LiaraClient, domain: str) -> dict:
    return client.request("POST", "/v1/domains/provision-ssl-certs", body={"domain": domain})


def guide(domain: str, cname_target: str | None = None, txt: str | None = None) -> dict:
    """Steps outside the API's reach, in Persian and English."""
    is_ir = domain.lower().endswith(".ir")
    target = cname_target or "<the value Liara shows for this domain>"
    records = [
        {"type": "ALIAS/CNAME", "name": "@", "value": target},
        {"type": "TXT", "name": "@", "value": txt or "<verification code Liara shows>"},
        {"type": "CNAME", "name": "_acme-challenge", "value": "<value Liara shows, for SSL>"},
    ]
    if is_ir:
        fa = [
            "وارد پنل ایرنیک شوید: https://www.nic.ir (با شناسهٔ ایرنیک و رمز).",
            "از منوی «دامنه‌ها» ← «دامنه‌های من» دامنه را انتخاب کنید.",
            f"در بخش ویرایش سرورهای نام، در فیلدهای «نام کارگزار» این دو را بنویسید: {LIARA_NS[0]} و {LIARA_NS[1]} (IP لازم نیست).",
            "به سؤال امنیتی پاسخ دهید و «ثبت تغییرات» را بزنید.",
            "قبل از تغییر، دامنه را در سرویس DNS لیارا بسازید و رکوردهای قبلی (مثل ایمیل/MX) را آنجا وارد کنید.",
            "اعمال تغییر معمولاً چند دقیقه تا ۲۴ ساعت (گاهی تا ۷۲ ساعت) طول می‌کشد.",
            "اگر دامنه را از نماینده خریده‌اید، شاید تغییر باید در پنل همان نماینده انجام شود.",
        ]
        en = [
            "Log in to the IRNIC panel at https://www.nic.ir.",
            "Domains → My domains → choose the domain.",
            f"In the name server fields enter {LIARA_NS[0]} and {LIARA_NS[1]} (no IPs).",
            "Answer the secret question and press Save.",
            "Create the zone in Liara DNS first and copy existing records (MX for email) there.",
            "It usually takes minutes to 24 h, sometimes up to 72 h.",
            "If a reseller manages the domain, change it in the reseller's panel.",
        ]
    else:
        fa = [
            "وارد پنل ثبت‌کنندهٔ دامنه شوید و بخش Nameservers را باز کنید.",
            f"گزینهٔ Custom DNS را انتخاب و {LIARA_NS[0]} و {LIARA_NS[1]} را وارد کنید.",
            "اگر DNSSEC فعال است، اول رکورد DS را حذف کنید.",
            "یا: DNS فعلی را نگه دارید و سه رکورد زیر را اضافه کنید (فقط اگر ALIAS/CNAME روی ریشه را پشتیبانی کند).",
        ]
        en = [
            "Open your registrar's Nameservers settings.",
            f"Choose Custom DNS and enter {LIARA_NS[0]} and {LIARA_NS[1]}.",
            "If DNSSEC is on, remove the DS record first.",
            "Or keep your DNS and add the three records below (only if it supports ALIAS/CNAME at the root).",
        ]
    return {"domain": domain, "registrar": "IRNIC (nic.ir)" if is_ir else "your registrar",
            "steps_fa": fa, "steps_en": en, "records": records,
            "after": "Then run `starcoach domain <app> <domain> --check` until the status is OK, "
                     "and `--ssl` for free HTTPS (Let's Encrypt).",
            "source": "https://docs.liara.ir/paas/domains/add-domain/"}
