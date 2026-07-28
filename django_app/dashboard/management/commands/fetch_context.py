from django.core.management.base import BaseCommand
from dashboard.models import NewsSource, RegulatorySource, NewsSignal, RegulatoryRule
import feedparser
import requests
from math import tanh

def severity_from_text(text: str) -> float:
    t = text.lower()
    hits = 0
    for k in ('crise','fraude','escândalo','queda','demissão','investiga','corrupção','rombo','lavagem','sanção'):
        if k in t:
            hits += 1
    return max(0.0, min(1.0, tanh(hits)))

def classify_category(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ('imposto','fiscal','tribut','iva','irs')):
        return 'fiscal'
    if any(k in t for k in ('trabalh','emprego','salário','contrato')):
        return 'trabalhista'
    if any(k in t for k in ('banco','finance','contábil','ifrs','gaap')):
        return 'financeira'
    return 'geral'

class Command(BaseCommand):
    def handle(self, *args, **options):
        created = 0
        for s in NewsSource.objects.filter(active=True):
            try:
                feed = feedparser.parse(s.url)
                for e in feed.entries[:20]:
                    title = getattr(e, 'title', '')
                    link = getattr(e, 'link', None)
                    sev = severity_from_text(title)
                    NewsSignal.objects.create(country=(s.country or None), sector=(s.sector or None), title=title, severity=sev, source_url=link, suggested_by_ai=True, ai_summary=title[:1000], ai_confidence=0.5 + sev*0.4)
                    created += 1
            except Exception:
                pass
        for s in RegulatorySource.objects.filter(active=True):
            try:
                r = requests.get(s.url, timeout=10)
                text = r.text[:2000]
                cat = classify_category(text)
                mult = 1.0 + (severity_from_text(text) * 0.3)
                RegulatoryRule.objects.create(country=(s.country or 'global'), regulation=s.title, alert_type='general', threshold_multiplier=mult, description=f'Categoria {cat}', active=False, suggested_by_ai=True, ai_summary=text, ai_confidence=0.5)
                created += 1
            except Exception:
                pass
        self.stdout.write(f'Created {created} context items')
