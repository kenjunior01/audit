from django.core.management.base import BaseCommand
from dashboard.models import NewsSource, RegulatorySource

class Command(BaseCommand):
    def handle(self, *args, **options):
        items_news = [
            {'title': 'Reuters Business', 'url': 'https://feeds.reuters.com/reuters/businessNews', 'country': None, 'sector': 'business', 'active': True},
            {'title': 'BBC Business', 'url': 'https://feeds.bbci.co.uk/news/business/rss.xml', 'country': None, 'sector': 'business', 'active': True},
        ]
        items_reg = [
            {'title': 'EU Tax Updates', 'url': 'https://ec.europa.eu/taxation_customs/news_en', 'country': 'EU', 'active': True},
        ]
        for it in items_news:
            NewsSource.objects.get_or_create(title=it['title'], defaults=it)
        for it in items_reg:
            RegulatorySource.objects.get_or_create(title=it['title'], defaults=it)
        self.stdout.write('Seeded default sources')
