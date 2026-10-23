"""What the Liara API cannot do. The assistant tells the user about these instead of guessing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Limit:
    id: str
    topic: str
    en: str
    fa: str
    source: str


LIMITS = [
    Limit("no-http-metrics", "monitoring",
          "Liara has no API for request counts, 5xx rates or response times. We probe the site URL ourselves.",
          "لیارا API برای تعداد درخواست، نرخ خطای ۵xx یا زمان پاسخ ندارد. خودمان آدرس سایت را بررسی می‌کنیم.",
          "docs/research/03-liara-logs-metrics.md"),
    Limit("no-restart-count", "monitoring",
          "The API does not report how many times an app restarted. We infer crashes from events and logs.",
          "API تعداد ری‌استارت‌های برنامه را گزارش نمی‌کند. از رویدادها و لاگ‌ها حدس می‌زنیم.",
          "docs/research/03-liara-logs-metrics.md"),
    Limit("no-health-result", "monitoring",
          "The live result of the health check is not exposed. We see only its effect (release state, events).",
          "نتیجهٔ زندهٔ health check در API نیست. فقط اثرش (وضعیت ریلیز، رویدادها) دیده می‌شود.",
          "docs/research/03-liara-logs-metrics.md"),
    Limit("no-rollback-api", "deploy",
          "There is no documented rollback API. To roll back we redeploy an older version.",
          "API مستندی برای بازگشت به نسخهٔ قبل وجود ندارد. برای بازگشت، نسخهٔ قدیمی را دوباره دیپلوی می‌کنیم.",
          "docs/research/02-liara-deploy.md"),
    Limit("no-notifications-api", "automation",
          "Console notifications have no API or webhook. Our `watch` command polls instead.",
          "اعلان‌های کنسول API یا وب‌هوک ندارند. فرمان watch ما به‌جای آن دوره‌ای بررسی می‌کند.",
          "docs/research/03-liara-logs-metrics.md"),
    Limit("registrar-outside", "domains",
          "Nameserver changes at the registrar (for example IRNIC for .ir) are done by you in the registrar panel.",
          "تغییر نیم‌سرورها در ثبت‌کنندهٔ دامنه (مثلاً ایرنیک برای .ir) را خودتان در پنل آن انجام می‌دهید.",
          "docs/research/04-domains-plans.md"),
    Limit("metric-units", "monitoring",
          "Metric units are not documented. Measured on a real app: CPU in cores, memory in bytes, one point per 30 s (F21).",
          "واحد متریک‌ها مستند نیست. روی برنامهٔ واقعی سنجیدیم: CPU بر حسب هسته، حافظه بر حسب بایت، هر ۳۰ ثانیه یک نقطه.",
          "docs/DECISIONS.md F21"),
    Limit("log-page", "monitoring",
          "The logs API returns at most 100 lines per call. We read the newest page; older lines need more calls.",
          "API لاگ در هر درخواست حداکثر ۱۰۰ خط می‌دهد. ما جدیدترین صفحه را می‌خوانیم.",
          "docs/DECISIONS.md F19"),
    Limit("payments", "billing",
          "Topping up the balance cannot be done through the API. You pay in the Liara console.",
          "شارژ حساب از طریق API ممکن نیست؛ باید در کنسول لیارا پرداخت کنید.",
          "docs/DECISIONS.md F12"),
]


def by_topic(topic: str | None = None) -> list[Limit]:
    return [l for l in LIMITS if topic in (None, l.topic)]
