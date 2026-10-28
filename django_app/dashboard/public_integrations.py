from email.utils import parsedate_to_datetime
import re
from urllib.parse import quote, urlsplit
from xml.etree import ElementTree

import requests
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .auth import IsViewerOrAbove

REQUEST_TIMEOUT = 8
PUBLIC_SERVICES = [
    {
        "id": "frankfurter",
        "category": "currency_finance",
        "name": "Frankfurter",
        "url": "https://frankfurter.dev/",
        "requires_key": False,
        "description": "Taxas de câmbio de referência do Banco Central Europeu.",
    },
    {
        "id": "rest-countries",
        "category": "geography",
        "name": "REST Countries",
        "url": "https://restcountries.com/",
        "requires_key": False,
        "description": "Dados de países; usa CountriesNow como alternativa se necessário.",
    },
    {
        "id": "countriesnow",
        "category": "geography",
        "name": "CountriesNow",
        "url": "https://countriesnow.space/",
        "requires_key": False,
        "description": "Fonte alternativa de países sem chave para maior disponibilidade.",
    },
    {
        "id": "open-meteo",
        "category": "weather",
        "name": "Open-Meteo",
        "url": "https://open-meteo.com/",
        "requires_key": False,
        "description": "Geocodificação e previsão meteorológica.",
    },
    {
        "id": "gdelt",
        "category": "news_risk",
        "name": "GDELT DOC",
        "url": "https://www.gdeltproject.org/",
        "requires_key": False,
        "description": "Pesquisa de notícias; Google News RSS é usado como alternativa.",
    },
    {
        "id": "google-news-rss",
        "category": "news_risk",
        "name": "Google News RSS",
        "url": "https://news.google.com/",
        "requires_key": False,
        "description": "Fonte alternativa de notícias públicas sem chave.",
    },
    {
        "id": "brasilapi-cnpj",
        "category": "regulation_company",
        "name": "BrasilAPI CNPJ",
        "url": "https://brasilapi.com.br/docs",
        "requires_key": False,
        "description": "Consulta de dados públicos de empresas brasileiras.",
    },
]

REGULATORY_SOURCES = [
    {
        "name": "Legislação Federal Brasileira (Planalto)",
        "country": "BR",
        "url": "https://www.planalto.gov.br/ccivil_03/",
        "type": "official_legal_repository",
    },
    {
        "name": "EUR-Lex",
        "country": "EU",
        "url": "https://eur-lex.europa.eu/",
        "type": "official_legal_repository",
    },
    {
        "name": "U.S. Securities and Exchange Commission",
        "country": "US",
        "url": "https://www.sec.gov/",
        "type": "official_regulatory_source",
    },
    {
        "name": "FATF Recommendations",
        "country": "GLOBAL",
        "url": "https://www.fatf-gafi.org/en/publications/Fatfrecommendations.html",
        "type": "official_regulatory_source",
    },
]


class PublicProviderError(Exception):
    pass


def _get_json(url, *, params=None):
    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise PublicProviderError from exc


def search_news_articles(query):
    try:
        data = _get_json(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={
                "query": query,
                "mode": "ArtList",
                "format": "json",
                "maxrecords": 10,
                "sort": "DateDesc",
            },
        )
        if isinstance(data, dict) and isinstance(data.get("articles"), list):
            return data["articles"]
    except PublicProviderError:
        pass

    try:
        response = requests.get(
            "https://news.google.com/rss/search",
            params={"q": query, "hl": "pt-PT", "gl": "PT", "ceid": "PT:pt-150"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
    except (requests.RequestException, ElementTree.ParseError, ValueError) as exc:
        raise PublicProviderError from exc

    articles = []
    for item in root.findall("./channel/item")[:10]:
        title = item.findtext("title")
        url = item.findtext("link")
        if not title or not url:
            continue
        published = item.findtext("pubDate") or ""
        try:
            parsed_date = parsedate_to_datetime(published)
            if parsed_date:
                published = parsed_date.isoformat()
        except (TypeError, ValueError, OverflowError):
            pass
        source = item.find("source")
        source_url = source.get("url", "") if source is not None else ""
        articles.append({
            "title": title,
            "url": url,
            "seendate": published,
            "domain": urlsplit(source_url).hostname or "",
            "description": item.findtext("description") or "",
        })
    return articles


def _provider_error(provider):
    return Response(
        {"error": "External public data provider is unavailable", "provider": provider},
        status=status.HTTP_502_BAD_GATEWAY,
    )


@api_view(["GET"])
@permission_classes([IsViewerOrAbove])
def public_services(request):
    return Response({
        "services": PUBLIC_SERVICES,
        "regulatory_sources": REGULATORY_SOURCES,
        "notice": (
            "Providers are independent public services; availability, rate limits, "
            "coverage and terms are controlled by each provider. Country and news "
            "lookups use a second no-key source when their primary provider fails."
        ),
        "privacy_notice": (
            "Search terms and lookup identifiers are sent to the selected external "
            "provider and, if it is unavailable, its listed fallback. Do not send "
            "confidential or personal information."
        ),
    })


@api_view(["GET"])
@permission_classes([IsViewerOrAbove])
def public_currency_rates(request):
    base = (request.query_params.get("base") or "EUR").upper()
    symbols = (request.query_params.get("symbols") or "").upper()
    if not re.fullmatch(r"[A-Z]{3}", base):
        return Response({"error": "base must be a three-letter currency code"}, status=400)
    if symbols and not re.fullmatch(r"[A-Z]{3}(,[A-Z]{3}){0,19}", symbols):
        return Response({"error": "symbols must be comma-separated currency codes"}, status=400)

    try:
        data = _get_json(
            "https://api.frankfurter.dev/v1/latest",
            params={"base": base, **({"symbols": symbols} if symbols else {})},
        )
    except PublicProviderError:
        return _provider_error("frankfurter")
    if not isinstance(data, dict):
        return _provider_error("frankfurter")
    return Response(data)


@api_view(["GET"])
@permission_classes([IsViewerOrAbove])
def public_country_lookup(request):
    query = (request.query_params.get("q") or "").strip()
    if not query or len(query) > 100:
        return Response({"error": "q is required and must be at most 100 characters"}, status=400)

    try:
        data = _get_json(
            f"https://restcountries.com/v3.1/name/{quote(query, safe='')}",
            params={"fields": "name,cca2,region,subregion,capital,currencies,latlng"},
        )
        if isinstance(data, list):
            return Response({"countries": data})
    except PublicProviderError:
        pass

    try:
        fallback_data = _get_json(
            "https://countriesnow.space/api/v0.1/countries/info",
            params={"returns": "name,iso2,iso3,capital,currency"},
        )
    except PublicProviderError:
        return _provider_error("countriesnow")
    if (
        not isinstance(fallback_data, dict)
        or fallback_data.get("error")
        or not isinstance(fallback_data.get("data"), list)
    ):
        return _provider_error("countriesnow")

    normalized_query = query.casefold()
    countries = []
    for country in fallback_data["data"]:
        if not isinstance(country, dict) or not isinstance(country.get("name"), str):
            continue
        name = country["name"]
        iso2 = country.get("iso2")
        if normalized_query not in name.casefold() and normalized_query != str(iso2 or "").casefold():
            continue
        capital = country.get("capital")
        countries.append({
            "name": {"common": name, "official": name},
            "cca2": iso2,
            "region": country.get("region"),
            "subregion": country.get("subregion"),
            "capital": [capital] if capital else [],
            "currencies": {},
            "latlng": [],
            "currency_code": country.get("currency"),
        })
    return Response({"countries": countries})


@api_view(["GET"])
@permission_classes([IsViewerOrAbove])
def public_weather(request):
    location = (request.query_params.get("location") or "").strip()
    if not location or len(location) > 100:
        return Response(
            {"error": "location is required and must be at most 100 characters"},
            status=400,
        )

    try:
        geocoding = _get_json(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location, "count": 1, "language": "en", "format": "json"},
        )
        if not isinstance(geocoding, dict):
            return _provider_error("open-meteo")
        matches = geocoding.get("results") or []
        if not matches:
            return Response({"error": "Location not found"}, status=404)
        place = matches[0]
        forecast = _get_json(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
                "timezone": "auto",
            },
        )
        if not isinstance(forecast, dict):
            return _provider_error("open-meteo")
    except PublicProviderError:
        return _provider_error("open-meteo")
    except (KeyError, TypeError):
        return _provider_error("open-meteo")

    return Response({"location": place, "weather": forecast})


@api_view(["GET"])
@permission_classes([IsViewerOrAbove])
def public_news_search(request):
    query = (request.query_params.get("q") or "").strip()
    if not query or len(query) > 200:
        return Response({"error": "q is required and must be at most 200 characters"}, status=400)

    try:
        articles = search_news_articles(query)
    except PublicProviderError:
        return _provider_error("gdelt-google-news")
    return Response({"query": query, "articles": articles})


@api_view(["GET"])
@permission_classes([IsViewerOrAbove])
def public_company_lookup(request):
    cnpj = re.sub(r"\D", "", request.query_params.get("cnpj") or "")
    if len(cnpj) != 14:
        return Response({"error": "cnpj must contain 14 digits"}, status=400)
    try:
        data = _get_json(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}")
    except PublicProviderError:
        return _provider_error("brasilapi-cnpj")
    if not isinstance(data, dict):
        return _provider_error("brasilapi-cnpj")
    return Response({"company": data})
