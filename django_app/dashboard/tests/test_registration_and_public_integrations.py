from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase
import requests
from rest_framework.test import APIClient

from dashboard.models import ApiToken, ContextProfile


class RegistrationApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.registration_data = {
            "name": "Audit User",
            "email": "auditor@example.com",
            "password": "StrongPass123!",
            "company_name": "Example Ltd",
            "sector": "Financial",
        }

    def test_registration_creates_user_profile_and_token(self):
        response = self.client.post(
            "/django/api/auth/register",
            self.registration_data,
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username="auditor@example.com")
        self.assertTrue(user.check_password(self.registration_data["password"]))
        self.assertTrue(ApiToken.objects.filter(
            token=response.data["token"],
            user_id=str(user.id),
            role="viewer",
        ).exists())
        profile = ContextProfile.objects.get(user_id=str(user.id))
        self.assertEqual(profile.department, "Example Ltd")
        self.assertEqual(profile.sector, "Financial")

    def test_registration_rejects_bad_email_or_short_password(self):
        invalid_email = {**self.registration_data, "email": "not-an-email"}
        response = self.client.post(
            "/django/api/auth/register", invalid_email, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.count(), 0)

        short_password = {**self.registration_data, "password": "short"}
        response = self.client.post(
            "/django/api/auth/register", short_password, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.count(), 0)

    def test_registration_is_case_insensitive_for_duplicate_email(self):
        self.client.post(
            "/django/api/auth/register", self.registration_data, format="json"
        )
        duplicate = {**self.registration_data, "email": "AUDITOR@EXAMPLE.COM"}

        response = self.client.post(
            "/django/api/auth/register", duplicate, format="json"
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(User.objects.count(), 1)

    def test_login_returns_the_registered_token(self):
        registration = self.client.post(
            "/django/api/auth/register", self.registration_data, format="json"
        )
        response = self.client.post(
            "/django/api/auth/login",
            {
                "email": self.registration_data["email"].upper(),
                "password": self.registration_data["password"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["token"], registration.data["token"])


class PublicIntegrationsApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.token = ApiToken.objects.create(
            token="public-api-test-token",
            user_id="test-user",
            role="viewer",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token.token}")

    def test_directory_lists_only_no_key_providers(self):
        response = self.client.get("/django/api/integrations/public")

        self.assertEqual(response.status_code, 200)
        providers = response.data["services"]
        self.assertTrue(providers)
        self.assertTrue(all(provider["requires_key"] is False for provider in providers))
        self.assertTrue(response.data["regulatory_sources"])

    def test_currency_endpoint_validates_and_returns_provider_data(self):
        provider_response = Mock()
        provider_response.json.return_value = {
            "amount": 1.0,
            "base": "EUR",
            "date": "2026-10-27",
            "rates": {"USD": 1.16},
        }
        with patch(
            "dashboard.public_integrations.requests.get",
            return_value=provider_response,
        ) as get:
            response = self.client.get(
                "/django/api/integrations/public/currencies?base=EUR&symbols=USD"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["rates"]["USD"], 1.16)
        get.assert_called_once()
        self.assertEqual(
            get.call_args.kwargs["params"],
            {"base": "EUR", "symbols": "USD"},
        )

        invalid = self.client.get(
            "/django/api/integrations/public/currencies?base=EURO"
        )
        self.assertEqual(invalid.status_code, 400)

    def test_provider_failure_is_reported_as_gateway_error(self):
        with patch(
            "dashboard.public_integrations.requests.get",
            side_effect=requests.Timeout,
        ):
            response = self.client.get(
                "/django/api/integrations/public/currencies"
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["provider"], "frankfurter")

    def test_public_integrations_require_authentication(self):
        self.client.credentials()

        response = self.client.get("/django/api/integrations/public")

        self.assertEqual(response.status_code, 403)

    def test_country_lookup_returns_public_country_data(self):
        country_data = [{
            "name": {"common": "Portugal"},
            "cca2": "PT",
            "region": "Europe",
        }]
        with patch(
            "dashboard.public_integrations.requests.get",
            return_value=Mock(json=lambda: country_data),
        ):
            response = self.client.get(
                "/django/api/integrations/public/countries?q=Portugal"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["countries"], country_data)

    def test_country_lookup_falls_back_when_rest_countries_is_unavailable(self):
        retired_response = Mock(json=lambda: {"success": False, "data": None})
        fallback_response = Mock(json=lambda: {
            "error": False,
            "data": [{
                "name": "Portugal",
                "iso2": "PT",
                "iso3": "PRT",
                "capital": "Lisbon",
                "currency": "EUR",
            }],
        })
        with patch(
            "dashboard.public_integrations.requests.get",
            side_effect=[retired_response, fallback_response],
        ):
            response = self.client.get(
                "/django/api/integrations/public/countries?q=Portugal"
            )

        self.assertEqual(response.status_code, 200)
        country = response.data["countries"][0]
        self.assertEqual(country["name"]["common"], "Portugal")
        self.assertEqual(country["cca2"], "PT")
        self.assertEqual(country["currency_code"], "EUR")

    def test_weather_lookup_geocodes_then_fetches_forecast(self):
        place = {"name": "Lisbon", "latitude": 38.72, "longitude": -9.14}
        forecast = {"current": {"temperature_2m": 20}}
        geocoding_response = Mock(json=lambda: {"results": [place]})
        forecast_response = Mock(json=lambda: forecast)
        with patch(
            "dashboard.public_integrations.requests.get",
            side_effect=[geocoding_response, forecast_response],
        ) as get:
            response = self.client.get(
                "/django/api/integrations/public/weather?location=Lisbon"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["location"], place)
        self.assertEqual(response.data["weather"], forecast)
        self.assertEqual(get.call_count, 2)

    def test_news_and_company_lookup_use_public_providers(self):
        news_response = Mock(json=lambda: {"articles": [{"title": "Public update"}]})
        company_response = Mock(json=lambda: {"razao_social": "Example Ltd"})
        with patch(
            "dashboard.public_integrations.requests.get",
            side_effect=[news_response, company_response],
        ):
            news = self.client.get(
                "/django/api/integrations/public/news?q=Example"
            )
            company = self.client.get(
                "/django/api/integrations/public/companies/br?cnpj=12.345.678%2F0001-90"
            )

        self.assertEqual(news.status_code, 200)
        self.assertEqual(news.data["articles"][0]["title"], "Public update")
        self.assertEqual(company.status_code, 200)
        self.assertEqual(company.data["company"]["razao_social"], "Example Ltd")

        invalid_company = self.client.get(
            "/django/api/integrations/public/companies/br?cnpj=123"
        )
        self.assertEqual(invalid_company.status_code, 400)

    def test_news_search_falls_back_to_google_news_rss(self):
        rss_response = Mock(content=(
            b"<rss><channel><item><title>Portugal news</title>"
            b"<link>https://news.example/article</link>"
            b"<pubDate>Tue, 27 Oct 2026 10:00:00 GMT</pubDate>"
            b"<source url='https://news.example'>Example News</source>"
            b"</item></channel></rss>"
        ))
        with patch(
            "dashboard.public_integrations.requests.get",
            side_effect=[requests.Timeout("GDELT unavailable"), rss_response],
        ):
            response = self.client.get(
                "/django/api/integrations/public/news?q=Portugal"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["articles"][0]["title"], "Portugal news")
        self.assertEqual(response.data["articles"][0]["domain"], "news.example")
